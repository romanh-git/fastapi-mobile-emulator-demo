# Makefile for the FastAPI Mobile Emulator Demo

.DEFAULT_GOAL := help

# Variables
PYTHON := python3
VENV_DIR := .venv
# Вже визначено шлях до pip та uvicorn всередині venv
PIP := $(VENV_DIR)/bin/pip
UVICORN := $(VENV_DIR)/bin/uvicorn
# ACTIVATE більше не потрібен для цих рецептів
# ACTIVATE := source $(VENV_DIR)/bin/activate
# # Handle Windows activation if needed (basic example)
# ifeq ($(OS),Windows_NT)
#     ACTIVATE = $(VENV_DIR)\\Scripts\\activate
#     PYTHON = python
# endif

.PHONY: all help venv install run clean

all: help

help:
	@echo "Available commands:"
	@echo "  make venv      - Create Python virtual environment '.venv'"
	@echo "  make install   - Install dependencies from requirements.txt into .venv"
	@echo "  make run       - Run the FastAPI server with Uvicorn (requires Ollama running)."
	@echo "                   Access the emulator at http://localhost:8000"
	@echo "                   Access Swagger API docs at http://localhost:8000/docs"
	@echo "                   Access ReDoc API docs at http://localhost:8000/redoc"
	@echo "  make clean     - Remove virtual environment and __pycache__ directories"

# Target to create virtual environment
# Checks if the directory exists first
$(VENV_DIR)/touchfile:
	@echo "Creating virtual environment in $(VENV_DIR)..."
	$(PYTHON) -m venv $(VENV_DIR)
	@touch $(VENV_DIR)/touchfile # Create a dummy file to track completion

venv: $(VENV_DIR)/touchfile
	@echo "Virtual environment '$(VENV_DIR)' is ready."

# Target to install dependencies
install: venv
	@echo "Installing dependencies from requirements.txt..."
	# Викликаємо pip напряму з venv, без активації
	$(PIP) install -r requirements.txt

# Target to run the development server
# Depends on install to ensure dependencies are met
run: install
	@echo "Starting FastAPI server on http://localhost:8000..."
	@echo "Ensure Ollama is running on http://localhost:11434!"
	@echo "Access Emulator: http://localhost:8000"
	@echo "Access API Docs (Swagger): http://localhost:8000/docs"
	@echo "Access API Docs (ReDoc): http://localhost:8000/redoc"
	# Викликаємо uvicorn напряму з venv, без активації
	$(UVICORN) main:app --reload --host 0.0.0.0 --port 8000

# Target to clean up generated files
clean:
	@echo "Cleaning up..."
	@rm -rf $(VENV_DIR)
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete
	@echo "Cleanup complete."