"""Manual/cron Phase 5 scheduled publishing worker for LOCAL STAGING ONLY.

Run: python -m backend.app.phase5_worker --once
A cron entry or process scheduler may invoke this command periodically.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from .config import Settings
from .db import make_engine, make_session_factory
from .models import PublishDeployment, utcnow
from .phase5 import perform_publish


def run_once(settings=None):
    settings=settings or Settings.from_env()
    engine=make_engine(settings.database_url)
    factory=make_session_factory(engine)
    if settings.publish_root:root=Path(settings.publish_root).resolve()
    elif settings.database_url.startswith('sqlite:///'):
        root=Path(settings.database_url[len('sqlite:///'):]).resolve().parent/'publishing'
    else:root=Path('instance/publishing').resolve()
    with factory() as db:
        due=db.query(PublishDeployment).filter(PublishDeployment.status=='scheduled',
            PublishDeployment.scheduled_for<=utcnow()).order_by(PublishDeployment.scheduled_for).limit(5).all()
        media_root=Path(settings.media_root).resolve() if settings.media_root else (Path(settings.database_url[len('sqlite:///'):]).resolve().parent/'media' if settings.database_url.startswith('sqlite:///') else Path('instance/media').resolve())
        results=[perform_publish(db,root,job,media_root) for job in due]
        return [(j.id,j.status) for j in results]


def main():
    parser=argparse.ArgumentParser(description='Run due LOCAL-STAGING CMS publication jobs')
    parser.add_argument('--once',action='store_true',required=True)
    parser.parse_args()
    for job,status in run_once():print(f'{job}: {status}')


if __name__=='__main__':main()
