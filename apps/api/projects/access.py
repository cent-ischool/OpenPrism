from django.core.exceptions import ValidationError
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import Membership, Project


def get_project(request, project_id, write=False):
    """Return the project if the user belongs to its workspace (with a write role when write=True)."""
    try:
        project = Project.objects.select_related('workspace').get(pk=project_id)
    except (Project.DoesNotExist, ValidationError):  # unknown or malformed id -> same 404
        raise NotFound('Project not found')
    user = request.user
    if getattr(user, 'is_guest', False):  # invite-link guest: exactly one project, role from the invite
        if str(project.id) != user.project_id:
            raise NotFound('Project not found')
        if write and not user.can_write:
            raise PermissionDenied('You have read-only access to this project.')
        return project
    membership = Membership.objects.filter(workspace=project.workspace, user=user).first()
    if membership is None:
        raise NotFound('Project not found')  # do not reveal existence
    if write and membership.role not in Membership.WRITE_ROLES:
        raise PermissionDenied('You have read-only access to this project.')
    return project


def user_projects(user):
    return Project.objects.filter(workspace__memberships__user=user)


class QueryTokenJWTAuthentication(JWTAuthentication):
    """Accept the access token (or an invite token) as ?token= as well as the Authorization header.

    Only for endpoints loaded by <img>/<object>/EventSource, which cannot set headers.
    """
    def authenticate(self, request):
        from collab.auth import InviteAuthentication, QueryInviteAuthentication
        for auth in (InviteAuthentication(), QueryInviteAuthentication()):
            result = auth.authenticate(request)
            if result is not None:
                return result
        result = super().authenticate(request)
        if result is not None:
            return result
        token = request.query_params.get('token')
        if not token:
            return None
        validated = self.get_validated_token(token)
        return self.get_user(validated), validated
