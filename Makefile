.PHONY: up down restart logs ps clean test reproduce dev llm edgex-feed

up:            ## Start the whole stack (no configuration required)
	docker compose up -d --build

down:          ## Stop the stack, keeping stored data
	docker compose down

restart:       ## Recreate the application services without touching data
	docker compose up -d --build --force-recreate qprime-analysis qprime-nlp qprime-query qprime-devices

logs:          ## Tail application logs
	docker compose logs -f qprime-analysis qprime-nlp qprime-query qprime-devices

ps:            ## Show container status
	docker compose ps

clean:         ## Stop the stack and delete all stored data and volumes
	docker compose down -v

edgex-feed:    ## Re-run the bundled feed through EdgeX instead of direct ingestion
	QPRIME_DEVICES_TRANSPORT=edgex docker compose up -d --force-recreate qprime-devices

llm:           ## Start the optional local LLM and pull its model
	docker compose --profile llm up -d ollama
	docker compose --profile llm exec ollama ollama pull "$${MODEL:-qwen2.5:7b-instruct-q4_K_M}"

test:          ## Run the retained algorithm and NLP tests
	python -m pytest tests/ -v

reproduce:     ## Run the paper's algorithms over its representative records
	python scripts/reproduce_paper.py

dev:           ## Run the Python APIs locally; run npm separately for the web UI
	python services/core/app.py & \
	python services/nlp/app.py & \
	wait
