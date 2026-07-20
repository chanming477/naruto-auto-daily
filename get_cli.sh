#!/bin/sh
# get_cli.sh — 复制 .NET native DLL 到 exe 同级目录
# (移植自 MaaAutoNaruto v1.3.41)
for d in runtimes/*/native; do
  [ -d "$d" ] && cp -f "$d"/* .
done
