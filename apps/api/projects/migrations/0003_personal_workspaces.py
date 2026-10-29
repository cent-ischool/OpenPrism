from django.db import migrations


def mark_personal(apps, schema_editor):
    """Workspaces created at registration (one owner, auto-named) become 'Personal' workspaces."""
    Workspace = apps.get_model('projects', 'Workspace')
    Membership = apps.get_model('projects', 'Membership')
    for ws in Workspace.objects.filter(name__endswith='workspace'):
        members = list(Membership.objects.filter(workspace=ws))
        if len(members) == 1 and members[0].role == 'owner' and ws.name.endswith("'s workspace"):
            ws.kind, ws.name, ws.color = 'personal', 'Personal', '#5b6573'
            ws.save(update_fields=['kind', 'name', 'color'])


class Migration(migrations.Migration):
    dependencies = [('projects', '0002_workspace_kind_invites')]
    operations = [migrations.RunPython(mark_personal, migrations.RunPython.noop)]
