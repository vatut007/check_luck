.PHONY: up down demo test lint shell logs

up:
	docker compose up --build

down:
	docker compose down

demo:
	docker compose up -d --build
	@echo "Waiting for the web service to finish migrations..."
	@until docker compose exec -T web python manage.py migrate --check >/dev/null 2>&1; do sleep 1; done
	docker compose exec web python manage.py seed_demo

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

shell:
	docker compose exec web python manage.py shell

logs:
	docker compose logs -f
