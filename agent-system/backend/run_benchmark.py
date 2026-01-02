#!/usr/bin/env python
import os
import sys
import django
import argparse
import json
from pathlib import Path

def setup_django():
    # Add project root to path
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()

def main():
    parser = argparse.ArgumentParser(description="Run Agent Benchmarks")
    parser.add_argument("--system", required=True, help="System name or ID")
    parser.add_argument("--model", action="append", help="Model names/IDs to test (can specify multiple)")
    parser.add_argument("--mode", action="append", default=["crs"], help="Agent modes (crs, direct)")
    parser.add_argument("--tasks", default=["read"], nargs="+", help="Task types (read, write)")
    parser.add_argument("--count", type=int, default=5, help="Number of tasks per suite")
    parser.add_argument("--user", required=True, help="Username or User ID")
    
    args = parser.parse_args()
    setup_django()
    
    from agent.models import System, LLMModel, User
    from agent.services.benchmark_service import run_benchmark
    
    # Resolve User
    try:
        if args.user.isdigit():
            user = User.objects.get(id=int(args.user))
        else:
            user = User.objects.get(username=args.user)
    except User.DoesNotExist:
        print(f"Error: User '{args.user}' not found.")
        return

    # Resolve System
    try:
        if args.system.isdigit():
            system = System.objects.get(id=int(args.system), user=user)
        else:
            system = System.objects.get(name=args.system, user=user)
    except System.DoesNotExist:
        print(f"Error: System '{args.system}' not found for user {user.username}.")
        return

    # Resolve Models
    models = []
    if args.model:
        for m in args.model:
            model = LLMModel.objects.filter(name=m, provider__user=user).first()
            if not model:
                model = LLMModel.objects.filter(model_id=m, provider__user=user).first()
            if model:
                models.append(model)
            else:
                print(f"Warning: Model '{m}' not found.")
    
    if not models:
        # Default to first available
        models = [LLMModel.objects.filter(provider__user=user).first()]
        print(f"No models specified. Using default: {models[0].name}")

    print(f"--- Starting Benchmark ---")
    print(f"System: {system.name}")
    print(f"Models: {[m.name for m in models]}")
    print(f"Modes: {args.mode}")
    print(f"Tasks: {args.tasks} (x{args.count})")
    
    try:
        payload = run_benchmark(
            system=system,
            models=models,
            agent_modes=args.mode,
            task_types=args.tasks,
            suite_size=args.count,
            user=user
        )
        
        print(f"\n--- Benchmark Complete ---")
        print(f"Run ID: {payload.run_id}")
        print(f"Status: {payload.status}")
        print(f"Summary: {json.dumps(payload.summary, indent=2)}")
        
        # Results location hint
        # Logic from benchmark_service to find path...
        from agent.services.benchmark_service import _find_run_dir
        run_dir = _find_run_dir(user, payload.run_id)
        if run_dir:
            print(f"\nResults stored in: {run_dir}")
            print(f"  - run.json")
            print(f"  - summary.json")
            print(f"  - results.json (in subdirs)")
            
    except Exception as e:
        print(f"\nError Running Benchmark: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
