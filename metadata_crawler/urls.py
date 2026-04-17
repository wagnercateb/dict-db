from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('connection/add/', views.add_connection, name='add_connection'),
    path('connection/<int:connection_id>/', views.connection_detail, name='connection_detail'),
    path('connection/<int:connection_id>/crawl/', views.crawl_database, name='crawl_database'),
    path('connection/<int:connection_id>/edit/', views.edit_connection, name='edit_connection'),
    path('connection/<int:connection_id>/delete/', views.delete_connection, name='delete_connection'),
    path('test-connections/', views.test_connections, name='test_connections'),
    path('table/<int:table_id>/', views.table_detail, name='table_detail'),
    path('lineage.json/', views.serve_lineage_json, name='serve_lineage_json'),
    path('field/<int:field_id>/', views.field_detail, name='field_detail'),
    path('search/advanced/', views.advanced_search, name='advanced_search'),
    path('search/', views.search_results, name='search_results'),
    path('search/<str:query>/', views.search_results, name='search_results'),
    path('comment/edit/<int:comment_id>/', views.edit_comment, name='edit_comment'),
    path('comment/delete/<int:comment_id>/', views.delete_comment, name='delete_comment'),
    path('toggle-maintenance/', views.toggle_maintenance, name='toggle_maintenance'),
]