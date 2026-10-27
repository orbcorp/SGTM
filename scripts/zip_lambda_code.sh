#! /bin/bash
set -e # Exit immediately if a command exits with a non-zero status.

# Install the production Python requirements as Linux wheels for the Lambda runtime,
# whatever platform this script runs on
rm -rf build/package
mkdir -p build/package
uv pip install \
  --python 3.13 \
  --python-platform x86_64-manylinux2014 \
  --target build/package \
  -r requirements.txt

# Zip the dependencies into the output archive
rm -f build/function.zip
(cd build/package && zip -r9 ../function.zip .)

# Zip the source code into the output archive
zip build/function.zip -r src/*
