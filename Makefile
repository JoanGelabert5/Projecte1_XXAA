.PHONY: init build-dev build-prod up-dev up-prod down status logs test verify unit package
ENV ?= dev
init build-dev build-prod up-dev up-prod package:
	./run.sh $@
down status logs test verify unit:
	./run.sh $@ $(ENV)
