#!/bin/sh
set -u

log()  { echo "[create_only] $*"; }
warn() { echo "[create_only][WARN] $*"; }

: "${OLLAMA_HOST:=http://ollama:11434}"
export OLLAMA_HOST

wait_ollama() {
  i=0
  until ollama list >/dev/null 2>&1; do
    i=$((i+1))
    if [ "$i" -ge 60 ]; then
      warn "ollama not ready after 60s, give up"
      return 1
    fi
    sleep 1
  done
  return 0
}

create_if_missing() {
  name="$1"
  modelfile="$2"

  if [ ! -f "$modelfile" ]; then
    warn "Modelfile missing, skip: $modelfile (model: $name)"
    return 0
  fi

  if ollama show "$name" >/dev/null 2>&1; then
    log "exists, skip: $name"
    return 0
  fi

  log "creating: $name (from $modelfile)"
  if ollama create "$name" -f "$modelfile"; then
    log "created: $name"
  else
    warn "create failed, continue: $name"
    return 0
  fi
}

log "OLLAMA_HOST=$OLLAMA_HOST"
if ! wait_ollama; then
  exit 1
fi

# 1) 出院 summary
create_if_missing "gemma-3n-privnurse-note-summary:v1.3" "/models/Modelfile_TCVGH_Summary_v1.3"

# 2) 出院 validation
create_if_missing "gemma-3n-privnurse-note-validation:v1" "/models/Modelfile_TCVGH_Validation_v1"

log "all done"
exit 0
