.PHONY: help build build-no-cache up up-all down ps logs refresh-requirements

help:
	@printf "Available targets:\n"
	@printf "  build               Build api, viewer, adhoc_scan_worker, and refresh_scheduler images\n"
	@printf "  build-no-cache      Build all service images without Docker cache\n"
	@printf "  up                  Start db, api, viewer, and adhoc_scan_worker\n"
	@printf "  up-all              Start db, api, viewer, adhoc_scan_worker, and refresh_scheduler\n"
	@printf "  down                Stop the Compose stack\n"
	@printf "  ps                  Show Compose service status\n"
	@printf "  logs                Follow Compose logs\n"
	@printf "  refresh-requirements  Re-export per-service requirements from Poetry\n"

build:
	docker compose build api viewer adhoc_scan_worker refresh_scheduler

build-no-cache:
	docker compose build --no-cache api viewer adhoc_scan_worker refresh_scheduler

up:
	docker compose up -d db api viewer adhoc_scan_worker

up-all:
	docker compose up -d db api viewer adhoc_scan_worker refresh_scheduler

down:
	docker compose down

ps:
	docker compose ps

logs:
	docker compose logs -f

refresh-requirements:
	./scripts/refresh_requirements.sh
