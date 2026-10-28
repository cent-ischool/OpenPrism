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
    membership = Membership.objects.filter(workspace=project.workspace, user=request.user).first()
    if membership is None:
        raise NotFound('Project not found')  # do not reveal existence
    if write and membership.role not in Membership.WRITE_ROLES:
        raise PermissionDenied('You have read-only access to this project.')
    return project


def user_projects(user):
    return Project.objects.filter(workspace__memberships__user=user)


class QueryTokenJWTAuthentication(JWTAuthentication):
    """Accept the access token as ?token= as well as the Authorization header.

    Only for endpoints loaded by <img>/<object>/EventSource, which cannot set headers.
    """
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            return result
        token = request.query_params.get('token')
        if not token:
            return None
        validated = self.get_validated_token(token)
        return self.get_user(validated), validated
