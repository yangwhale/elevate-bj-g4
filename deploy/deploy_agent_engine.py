#!/usr/bin/env python3
"""Deploy the agent to Vertex AI Agent Engine.

Terraform cannot create an Agent Engine instance (SDD.md C.1), so deployment
runs through the SDK. This script is the deployment; the resource it creates is
recorded in deploy/PROVISIONED.md.
"""
import os
import sys

import vertexai
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import AdkApp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent.agent import root_agent  # noqa: E402

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "chris-pgp-host")
REGION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
STAGING = os.environ.get("STAGING_BUCKET", f"gs://{PROJECT}-elevate-staging")

vertexai.init(project=PROJECT, location=REGION, staging_bucket=STAGING)

app = AdkApp(agent=root_agent, enable_tracing=True)

remote = agent_engines.create(
    agent_engine=app,
    display_name="elevate-hr-agent",
    description="Project Elevate HR & IT assistant (capstone). Safe to delete.",
    requirements=[
        "google-cloud-aiplatform[adk,agent_engines]",
        "google-adk",
        "python-dotenv",
    ],
    extra_packages=["agent", "knowledge"],
    env_vars={
        "GEMINI_MODEL": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        "GOOGLE_GENAI_USE_VERTEXAI": "TRUE",
        "DEFAULT_EMPLOYEE_ID": "EMP-1002",
    },
)

print("RESOURCE_NAME=" + remote.resource_name)
