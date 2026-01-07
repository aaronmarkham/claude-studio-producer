#!/bin/bash
# Quick agent/workflow invocation helper

set -e

ENDPOINT=${ENDPOINT:-http://localhost:8000}

case "$1" in
  agent)
    if [ -z "$2" ]; then
      echo "Error: Agent name required"
      echo "Usage: $0 agent <name> '<json_body>'"
      exit 1
    fi

    if [ -z "$3" ]; then
      echo "Error: JSON body required"
      echo "Usage: $0 agent <name> '<json_body>'"
      exit 1
    fi

    echo "[INFO] Invoking agent: $2"
    curl -s -X POST "$ENDPOINT/agents/$2/run" \
      -H "Content-Type: application/json" \
      -d "$3" | jq
    ;;

  workflow)
    if [ -z "$2" ]; then
      echo "Error: Workflow name required"
      echo "Usage: $0 workflow <name> '<json_body>'"
      exit 1
    fi

    if [ -z "$3" ]; then
      echo "Error: JSON body required"
      echo "Usage: $0 workflow <name> '<json_body>'"
      exit 1
    fi

    echo "[INFO] Invoking workflow: $2"
    curl -s -X POST "$ENDPOINT/workflows/$2/run" \
      -H "Content-Type: application/json" \
      -d "$3" | jq
    ;;

  status)
    if [ -z "$2" ]; then
      echo "Error: Run ID required"
      echo "Usage: $0 status <run_id>"
      exit 1
    fi

    curl -s "$ENDPOINT/workflows/status/$2" | jq
    ;;

  artifacts)
    if [ -z "$2" ]; then
      # List all artifacts
      curl -s "$ENDPOINT/artifacts" | jq
    else
      # Get specific run artifacts
      curl -s "$ENDPOINT/artifacts/runs/$2" | jq
    fi
    ;;

  health)
    curl -s "$ENDPOINT/health" | jq
    ;;

  list)
    case "$2" in
      agents)
        curl -s "$ENDPOINT/agents" | jq
        ;;
      workflows)
        curl -s "$ENDPOINT/workflows" | jq
        ;;
      *)
        echo "Usage: $0 list {agents|workflows}"
        exit 1
        ;;
    esac
    ;;

  *)
    echo "Claude Studio Producer - API Invocation Helper"
    echo ""
    echo "Usage: $0 {command} [args]"
    echo ""
    echo "Commands:"
    echo "  agent <name> '<json>'      Invoke an agent"
    echo "  workflow <name> '<json>'   Start a workflow"
    echo "  status <run_id>            Check workflow status"
    echo "  artifacts [run_id]         List artifacts"
    echo "  health                     Check server health"
    echo "  list {agents|workflows}    List available resources"
    echo ""
    echo "Examples:"
    echo "  # Run producer agent"
    echo "  $0 agent producer '{\"inputs\":{\"user_request\":\"test video\",\"total_budget\":100}}'"
    echo ""
    echo "  # Start full production workflow"
    echo "  $0 workflow full_production '{\"inputs\":{\"user_request\":\"demo\",\"total_budget\":50},\"run_async\":true}'"
    echo ""
    echo "  # Check workflow status"
    echo "  $0 status abc123"
    echo ""
    echo "  # List agents"
    echo "  $0 list agents"
    echo ""
    echo "Environment:"
    echo "  ENDPOINT    API endpoint (default: http://localhost:8000)"
    exit 1
    ;;
esac
