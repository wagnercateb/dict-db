import json
import os
import tempfile

from django.test import TestCase

from . import lineage


class DmlModifierExtractionTests(TestCase):
    def test_insert_into(self):
        mods = lineage.extract_dml_modifiers(
            'reprebh', 'INSERT INTO dbo.COSIF_CONTAS_FINAIS (a) VALUES (1)'
        )
        self.assertEqual(
            mods, [{'command': 'INSERT', 'table': 'reprebh.dbo.cosif_contas_finais'}]
        )

    def test_insert_without_into(self):
        mods = lineage.extract_dml_modifiers('reprebh', 'INSERT dbo.T SELECT 1')
        self.assertEqual(mods, [{'command': 'INSERT', 'table': 'reprebh.dbo.t'}])

    def test_select_into(self):
        mods = lineage.extract_dml_modifiers(
            'reprebh', 'SELECT a, b INTO dbo.T2 FROM dbo.T'
        )
        self.assertEqual(mods, [{'command': 'SELECT INTO', 'table': 'reprebh.dbo.t2'}])

    def test_select_from_is_not_select_into(self):
        mods = lineage.extract_dml_modifiers('reprebh', 'SELECT a FROM dbo.T')
        self.assertEqual(mods, [])

    def test_update(self):
        mods = lineage.extract_dml_modifiers('reprebh', 'UPDATE dbo.T SET a = 1')
        self.assertEqual(mods, [{'command': 'UPDATE', 'table': 'reprebh.dbo.t'}])

    def test_update_alias_resolved_from_from_clause(self):
        sql = (
            'UPDATE t SET t.a = s.a '
            'FROM dbo.COSIF_CONTAS_FINAIS t '
            'JOIN dbo.S s ON t.id = s.id'
        )
        mods = lineage.extract_dml_modifiers('reprebh', sql)
        self.assertEqual(
            mods, [{'command': 'UPDATE', 'table': 'reprebh.dbo.cosif_contas_finais'}]
        )

    def test_delete_from(self):
        mods = lineage.extract_dml_modifiers('reprebh', 'DELETE FROM dbo.T WHERE a = 1')
        self.assertEqual(mods, [{'command': 'DELETE', 'table': 'reprebh.dbo.t'}])

    def test_delete_alias_resolved(self):
        sql = 'DELETE t FROM dbo.T t WHERE t.a IS NULL'
        mods = lineage.extract_dml_modifiers('reprebh', sql)
        self.assertEqual(mods, [{'command': 'DELETE', 'table': 'reprebh.dbo.t'}])

    def test_three_part_identifier_kept(self):
        mods = lineage.extract_dml_modifiers(
            'reprebh', 'UPDATE outra_db.dbo.T SET a = 1'
        )
        self.assertEqual(mods, [{'command': 'UPDATE', 'table': 'outra_db.dbo.t'}])

    def test_db_prefix_is_lowercased(self):
        mods = lineage.extract_dml_modifiers(
            'REPREBH', 'UPDATE dbo.T SET a = 1'
        )
        self.assertEqual(mods, [{'command': 'UPDATE', 'table': 'reprebh.dbo.t'}])

    def test_cross_database_omitted_schema(self):
        mods = lineage.extract_dml_modifiers(
            'reprebh',
            'INSERT INTO DESIG_D5_Monitoramento_de_Limites..var_externa_capital_tb3 '
            'SELECT 1',
        )
        self.assertEqual(mods, [{
            'command': 'INSERT',
            'table': 'desig_d5_monitoramento_de_limites.dbo.var_externa_capital_tb3',
        }])

    def test_double_quoted_identifier(self):
        mods = lineage.extract_dml_modifiers('reprebh', 'INSERT INTO "dbo"."T" VALUES (1)')
        self.assertEqual(mods, [{'command': 'INSERT', 'table': 'reprebh.dbo.t'}])

    def test_select_followed_by_insert_is_not_select_into(self):
        sql = "SELECT 'a--b' AS x;\nINSERT INTO dbo.T VALUES (1)"
        mods = lineage.extract_dml_modifiers('reprebh', sql)
        self.assertEqual(mods, [{'command': 'INSERT', 'table': 'reprebh.dbo.t'}])

    def test_cte_target_is_ignored(self):
        sql = 'WITH cte AS (SELECT 1 AS a) UPDATE cte SET a = 2'
        self.assertEqual(lineage.extract_dml_modifiers('reprebh', sql), [])

    def test_temp_table_is_ignored(self):
        sql = 'SELECT a INTO #tmp FROM dbo.T'
        self.assertEqual(lineage.extract_dml_modifiers('reprebh', sql), [])

    def test_string_literal_is_ignored(self):
        sql = "EXEC('INSERT INTO dbo.T VALUES (1)')"
        self.assertEqual(lineage.extract_dml_modifiers('reprebh', sql), [])

    def test_deduplication(self):
        sql = 'UPDATE dbo.T SET a=1; UPDATE dbo.T SET a=2'
        mods = lineage.extract_dml_modifiers('reprebh', sql)
        self.assertEqual(mods, [{'command': 'UPDATE', 'table': 'reprebh.dbo.t'}])


class TableModifierIndexTests(TestCase):
    def test_grouping_by_table(self):
        routines = [
            {
                'routine': 'reprebh.dbo.SP_A',
                'routine_type': 'PROCEDURE',
                'modifiers': [
                    {'command': 'INSERT', 'table': 'reprebh.dbo.t'},
                    {'command': 'UPDATE', 'table': 'reprebh.dbo.t'},
                ],
            },
            {
                'routine': 'reprebh.dbo.SP_B',
                'routine_type': 'PROCEDURE',
                'modifiers': [{'command': 'DELETE', 'table': 'reprebh.dbo.t'}],
            },
        ]
        index = lineage.build_table_modifier_index(routines)
        self.assertEqual(len(index), 1)
        self.assertEqual(index[0]['table'], 'reprebh.dbo.t')
        commands = sorted(m['command'] for m in index[0]['modifiers'])
        self.assertEqual(commands, ['DELETE', 'INSERT', 'UPDATE'])


class _FakeCursor:
    def __init__(self):
        self._query = None

    def execute(self, query, *args):
        self._query = 'views' if 'sys.views' in query else 'routines'

    def fetchall(self):
        if self._query == 'views':
            return [('dbo', 'vw_x', 'SELECT a FROM dbo.COSIF_CONTAS_FINAIS')]
        # SQL Server devolve o tipo como CHAR(2) com padding ("P ").
        return [(
            'dbo',
            'Atualiza_COSIF_Contas_Finais',
            'P ',
            'INSERT INTO dbo.COSIF_CONTAS_FINAIS SELECT 1',
        )]


class _CrossDbCursor:
    def execute(self, query, *args):
        self._query = query

    def fetchall(self):
        if 'sys.views' in self._query:
            return []
        # SP em desig_d5_limites gravando em uma tabela de DESIG_D5.
        return [(
            'dbo',
            'DLO_Carga_das_Tabelas_Limites1',
            'P ',
            'INSERT INTO DESIG_D5_Monitoramento_de_Limites..DLO_Detalhamento_ACP_contraciclico '
            'SELECT 1',
        )]


class CrossDatabaseTests(TestCase):
    def test_cross_database_modifier_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            lineage_path = os.path.join(tmp, 'lineage.json')
            modifiers_path = os.path.join(tmp, 'modifiers.json')

            lineage.update_lineage_files(
                'desig_d5_limites', _CrossDbCursor(), lineage_path, modifiers_path,
                databases=['desig_d5_limites'],
            )

            data = json.load(open(modifiers_path, encoding='utf-8'))
            entry = next(
                item for item in data
                if item['table'] == 'desig_d5_monitoramento_de_limites.dbo.dlo_detalhamento_acp_contraciclico'
            )
            self.assertEqual(
                entry['modifiers'][0]['routine'],
                'desig_d5_limites.dbo.DLO_Carga_das_Tabelas_Limites1',
            )
            self.assertEqual(entry['modifiers'][0]['command'], 'INSERT')


class UpdateLineageFilesTests(TestCase):
    def test_merges_without_deleting_existing_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            lineage_path = os.path.join(tmp, 'lineage.json')
            modifiers_path = os.path.join(tmp, 'modifiers.json')
            with open(lineage_path, 'w', encoding='utf-8') as handle:
                json.dump([{'object': 'other.dbo.v', 'sources': [], 'status': 'success'}], handle)
            with open(modifiers_path, 'w', encoding='utf-8') as handle:
                json.dump([{'table': 'other.dbo.t', 'modifiers': []}], handle)

            summary = lineage.update_lineage_files(
                'reprebh', _FakeCursor(), lineage_path, modifiers_path
            )

            self.assertEqual(summary['views'], 1)
            self.assertEqual(summary['tables_modified'], 1)

            stored_lineage = json.load(open(lineage_path, encoding='utf-8'))
            self.assertEqual(len(stored_lineage), 2)

            stored_modifiers = json.load(open(modifiers_path, encoding='utf-8'))
            self.assertEqual(len(stored_modifiers), 2)
            entry = next(
                item for item in stored_modifiers
                if item['table'] == 'reprebh.dbo.cosif_contas_finais'
            )
            self.assertEqual(entry['modifiers'][0]['command'], 'INSERT')
            self.assertEqual(entry['modifiers'][0]['routine_type'], 'PROCEDURE')
