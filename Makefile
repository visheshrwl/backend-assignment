.PHONY: up down logs test

up:
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f api

test:
	# Run tests locally (requires env setup) or inside container
	# Assuming user wants to run locally for now or via another docker command
	pytest
