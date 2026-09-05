.PHONY: help up down logs rebuild clean test selftest dev-backend dev-frontend backup restore migrate-normalize

help:
	@echo "NETZWACHE"
	@echo "  make up            - Docker-Stack starten (Dashboard: http://localhost:8080)"
	@echo "  make down          - Stack stoppen"
	@echo "  make logs          - Backend-Logs verfolgen"
	@echo "  make rebuild       - Images neu bauen und starten"
	@echo "  make clean         - Stack + Datenbank-Volume löschen"
	@echo "  make test          - Backend-Tests"
	@echo "  make selftest      - Quellen gegen echte Endpunkte prüfen"
	@echo "  make dev-backend   - Backend lokal mit SQLite (Port 8000)"
	@echo "  make dev-frontend  - Vite-Dev-Server (Port 5173)"
	@echo "  make backup        - sofortiger DB-Dump nach ./backups (zusätzlich zum täglichen Auto-Backup)"
	@echo "  make restore FILE=backups/netzwache-....sql.gz - DB aus einem Dump wiederherstellen"
	@echo "  make migrate-normalize - bestehende Posts in post_categories/post_tags nachtragen (einmalig, idempotent)"

up:
	@test -f .env || cp .env.example .env
	docker compose up --build -d
	@echo "Dashboard: http://localhost:8080   API-Doku: http://localhost:8000/docs"

down:
	docker compose down

logs:
	docker compose logs -f backend

rebuild:
	docker compose up --build --force-recreate -d

clean:
	docker compose down -v

test:
	cd backend && python -m pytest

selftest:
	cd backend && python -m app.selftest

dev-backend:
	cd backend && DATABASE_URL=sqlite+aiosqlite:///./netzwache.db uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

backup:
	@mkdir -p backups
	docker exec netzwache-db pg_dump -U netzwache -d netzwache | gzip > backups/netzwache-$$(date -u +%Y%m%d-%H%M%S)-manual.sql.gz
	@echo "Backup geschrieben nach ./backups/"

restore:
	@test -n "$(FILE)" || { echo "Nutzung: make restore FILE=backups/netzwache-....sql.gz"; exit 1; }
	gunzip -c $(FILE) | docker exec -i netzwache-db psql -U netzwache -d netzwache

migrate-normalize:
	docker exec netzwache-backend python -m app.migrate_normalize
