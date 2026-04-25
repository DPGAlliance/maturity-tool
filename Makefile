.PHONY: help build build-no-cache up up-all down ps logs refresh-requirements

help:
	@printf "Available targets:\n"
	@printf "  build               Build api, viewer, and refresh_scheduler images\n"
	@printf "  build-no-cache      Build all service images without Docker cache\n"
	@printf "  up                  Start db, api, and viewer\n"
	@printf "  up-all              Start db, api, viewer, and refresh_scheduler\n"
	@printf "  down                Stop the Compose stack\n"
	@printf "  ps                  Show Compose service status\n"
	@printf "  logs                Follow Compose logs\n"
	@printf "  refresh-requirements  Re-export per-service requirements from Poetry\n"

build:
	docker compose build api viewer refresh_scheduler

build-no-cache:
	docker compose build --no-cache api viewer refresh_scheduler

up:
	docker compose up -d db api viewer

up-all:
	docker compose up -d db api viewer refresh_scheduler

down:
	docker compose down

ps:
	docker compose ps

logs:
	docker compose logs -f

refresh-requirements:
	./scripts/refresh_requirements.sh
