from django import forms
from .models import DatabaseConnection, MetadataComment


# objeto logger do python foi instanciado no módulo utils
from .utils import logger
logger.info("This was logged from forms.py module")


class DatabaseConnectionForm(forms.ModelForm):
    class Meta:
        model = DatabaseConnection
        fields = ['name', 'database_type', 'server', 'database', 'username']
        labels = {
            'name': 'Nome da Conexão',
            'database_type': 'Tipo de Banco de Dados',
            'server': 'Servidor',
            'database': 'Banco de Dados',
            'username': 'Usuário',
        }
        help_texts = {
            'username': 'Deixe em branco para usar Autenticação do Windows (apenas para SQL Server)',
        }


class CrawlCredentialsForm(forms.Form):
    username = forms.CharField(required=False, label='Usuário')
    password = forms.CharField(widget=forms.PasswordInput(), required=False, label='Senha')


class MetadataCommentForm(forms.ModelForm):
    class Meta:
        model = MetadataComment
        fields = ['comment']
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 5, 'cols': 120, 'class': 'form-control form-control-sm', 'style': 'width: 100%;'}),
        }


class SearchForm(forms.Form):
    search_query = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Pesquisar metadados...', 'class': 'form-control'})
    )


class AdvancedSearchForm(forms.Form):
    connections = forms.MultipleChoiceField(
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'connection-checkboxes'}),
        label='Conexões'
    )
    table_name = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nome da tabela/view'}))
    table_schema = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Schema'}))
    table_type = forms.MultipleChoiceField(
        required=False,
        choices=[('TABLE', 'TABLE'), ('VIEW', 'VIEW')],
        widget=forms.CheckboxSelectMultiple,
        initial=['TABLE', 'VIEW']
    )
    field_name = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nome do campo'}))
    field_data_type = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tipo de dado'}))
    field_table_type = forms.MultipleChoiceField(
        required=False,
        choices=[('TABLE', 'TABLE'), ('VIEW', 'VIEW')],
        widget=forms.CheckboxSelectMultiple,
        initial=['TABLE', 'VIEW'],
        label='Tipo (TABLE/VIEW)'
    )
    exclude_table_terms = forms.CharField(
        required=False,
        initial="_bak, temp_",
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'ex.: _bak, temp_ (separar por vírgula)'})
    )
    comment_text = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Texto do comentário'}))
    comment_type = forms.MultipleChoiceField(
        required=False,
        choices=[('TABLE', 'TABLE'), ('FIELD', 'FIELD'), ('CONNECTION', 'CONNECTION')],
        widget=forms.CheckboxSelectMultiple,
        initial=['TABLE', 'FIELD', 'CONNECTION']
    )
    comment_authors = forms.MultipleChoiceField(
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'author-checkboxes'}),
        label='Autores do comentário'
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate connection choices dynamically
        connection_choices = [(str(conn.id), conn.name) for conn in DatabaseConnection.objects.all()]
        self.fields['connections'].choices = connection_choices
        # Select all connections by default
        self.fields['connections'].initial = [choice[0] for choice in connection_choices]
        
        # Populate comment author choices dynamically
        author_qs = MetadataComment.objects.select_related('user').values_list('user__id', 'user__username').distinct()
        author_choices = [(str(uid), uname) for uid, uname in author_qs]
        self.fields['comment_authors'].choices = author_choices
        self.fields['comment_authors'].initial = [choice[0] for choice in author_choices]


#autenticação sem senha
# forms.py

from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()

# Django’s LoginView expects the form you provide (form_class) to be compatible with its expectations, specifically AuthenticationForm, which has this signature:
#   def __init__(self, request=None, *args, **kwargs):
# So, when you subclass forms.Form (which normally only expects *args, **kwargs), Django breaks when it tries to pass request=.

class UsernameOnlyAuthenticationForm(forms.Form):
    username = forms.CharField()

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request  # store if needed

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get("username")

        #Wagner hack: Auto-create user if username doesn't exist
        if not username:
            raise forms.ValidationError("Please enter a username.")
        # Try to get the user; if not exist, create one
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                # create_user(...) would set a usable/unusable password accordingly;
                # get_or_create uses defaults dict for new instances
            }
        )
        if created:
            # ensure unusable password so no password auth is possible
            user.set_unusable_password()
            user.is_active = True
            user.save()
        self.user = user
        return cleaned_data

        # código original: checa se user está na base
        # if username:
        #     try:
        #         self.user = User.objects.get(username=username)
        #     except User.DoesNotExist:
        #         raise forms.ValidationError("Invalid username")
        # return cleaned_data

    def get_user(self):
        return getattr(self, 'user', None)