.PHONY: run test build stop logs clean help

help:           ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

build:          ## Build the Docker image
	docker compose build

run:            ## Start ZAP + orchestrator (one command)
	docker compose up --build

test:           ## Run pytest inside Docker (no ZAP needed)
	docker compose run --rm --no-deps test

stop:           ## Stop all containers
	docker compose down

logs:           ## Tail orchestrator logs
	docker compose logs -f orchestrator

clean:          ## Remove containers, images, and report output
	docker compose down --rmi local --volumes --remove-orphans
