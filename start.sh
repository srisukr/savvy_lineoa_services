#!/bin/bash
gunicorn webhook:app --bind 0.0.0.0:$PORT
