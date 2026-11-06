#!/bin/bash
c(){ grep -rE --include='*.py' "$2" "$1" 2>/dev/null | wc -l | tr -d ' '; }
printf "%-30s %5s %5s %5s %5s %5s %5s %5s %5s %5s %5s %5s %5s\n" project fapi flask djpth drf reqs httpx aioht celry boto3 click argp grpc
for d in "$@"; do
printf "%-30s %5s %5s %5s %5s %5s %5s %5s %5s %5s %5s %5s %5s\n" $(basename $d) \
 $(c $d '@[a-z_]*(router|app)\.(get|post|put|patch|delete|api_route|websocket)\(') \
 $(c $d '@[a-z_]*\.route\(') $(c $d '^\s*(re_)?path\(') $(c $d '\.register\(r?["'"'"']') \
 $(c $d 'requests\.(get|post|put|delete|patch|request|Session)\b') $(c $d 'httpx\.(get|post|request|AsyncClient|Client)\b') \
 $(c $d 'aiohttp\.ClientSession') $(c $d '@[a-z_.]*(task|shared_task|actor)\b|\.delay\(|apply_async|\.send\(') \
 $(c $d 'boto3\.(client|resource)') $(c $d '@click\.(command|group)|@[a-z_]+\.command\(|typer\.Typer') \
 $(c $d 'ArgumentParser|add_parser\(') $(c $d 'add_[A-Za-z]+Servicer_to_server|Stub\(')
done
