from django.urls import path

from . import views

urlpatterns = [
    path('llm', views.llm_endpoint),
    path('agent/run', views.agent_run),
    path('vision/latex', views.vision_latex),
    path('plot/from-table', views.plot_from_table),
    path('arxiv/search', views.arxiv_search),
    path('arxiv/bibtex', views.arxiv_bibtex),
]
