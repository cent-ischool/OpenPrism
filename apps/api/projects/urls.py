from django.urls import include, path

from . import views as v

urlpatterns = [
    path('projects', v.projects_collection),
    path('projects/import-zip', v.import_zip),
    path('projects/<uuid:pk>', v.project_trash_delete),
    path('projects/<uuid:pk>/permanent', v.project_permanent_delete),
    path('projects/<uuid:pk>/rename-project', v.rename_project),
    path('projects/<uuid:pk>/copy', v.copy_project),
    path('projects/<uuid:pk>/tags', v.project_tags),
    path('projects/<uuid:pk>/archive', v.project_archive),
    path('projects/<uuid:pk>/trash', v.project_trash),
    path('projects/<uuid:pk>/tree', v.tree),
    path('projects/<uuid:pk>/file-order', v.file_order),
    path('projects/<uuid:pk>/file', v.file_item),
    path('projects/<uuid:pk>/blob', v.blob),
    path('projects/<uuid:pk>/upload', v.upload),
    path('projects/<uuid:pk>/files', v.all_files),
    path('projects/<uuid:pk>/folder', v.create_folder),
    path('projects/<uuid:pk>/rename', v.rename_path),
    path('projects/<uuid:pk>/template', v.apply_template),
    path('projects/<uuid:pk>/convert-template', v.convert_template),
    path('', include('templates_app.urls')),
]
