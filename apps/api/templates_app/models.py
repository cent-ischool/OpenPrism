from django.db import models


class Template(models.Model):
    """Replaces templates/manifest.json. Files live in S3 under templates/<id>/."""
    id = models.CharField(primary_key=True, max_length=100)
    label = models.CharField(max_length=200)
    main_file = models.CharField(max_length=300, default='main.tex')
    category = models.CharField(max_length=100, blank=True, default='')
    description = models.TextField(blank=True, default='')
    description_en = models.TextField(blank=True, default='')
    tags = models.JSONField(default=list, blank=True)
    author = models.CharField(max_length=200, blank=True, default='')
    featured = models.BooleanField(default=False)
    builtin = models.BooleanField(default=False)

    @property
    def s3_prefix(self):
        return f'templates/{self.id}/'
