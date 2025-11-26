"""
Celery worker configuration - import tasks here to register them
"""
from celery_app import celery
import tasks  # This imports and registers all tasks

# This file is only used when starting the worker