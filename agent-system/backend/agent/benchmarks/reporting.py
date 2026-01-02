import json
import os
from glob import glob
from typing import List, Dict, Any
from pathlib import Path
from collections import defaultdict
import statistics

class ResultAggregator:
    """
    Analyzes benchmark traces and generates reports.
    """
    
    def __init__(self, trace_dir: str):
        self.trace_dir = trace_dir
        self.traces = []
        
    def load_traces(self):
        """Load all JSON traces from directory"""
        if not os.path.exists(self.trace_dir):
            return
            
        files = glob(os.path.join(self.trace_dir, "trace_*.json"))
        for f in files:
            try:
                with open(f, 'r', encoding='utf-8') as fd:
                    data = json.load(fd)
                    self.traces.append(data)
            except Exception as e:
                print(f"Error loading {f}: {e}")
                
    def compute_metrics(self) -> Dict[str, Any]:
        """Compute aggregate metrics per strategy/scenario"""
        stats = defaultdict(lambda: {
            "count": 0, "success": 0, "durations": [], "steps": [], "patches": 0
        })
        
        for t in self.traces:
            key = f"{t.get('scenario_id')}_{t.get('strategy')}"
            
            # Determine success
            # Success logic depends on trace final status OR verification results
            # For now assume metadata.status or fallback to trace end
            steps = t.get('steps', [])
            status = "unknown"
            # Look for verification pass
            verified = False
            for s in steps:
                if s['kind'] == 'VERIFICATION':
                    if s['content'].get('ok') or s['content'].get('overall_ok'):
                        verified = True
            
            # Also check manual metadata override
            meta_status = t.get('metadata', {}).get('status')
            is_success = verified or (meta_status == 'success' and 'ERROR' not in [s['kind'] for s in steps])

            duration = t.get('end_time', 0) - t.get('start_time', 0)
            if duration < 0: duration = 0
            
            s = stats[key]
            s['count'] += 1
            if is_success: s['success'] += 1
            s['durations'].append(duration)
            s['steps'].append(len(steps))
            
        # Aggregation
        report = {}
        for key, val in stats.items():
            if val['count'] > 0:
                report[key] = {
                    "total_runs": val['count'],
                    "success_rate": val['success'] / val['count'],
                    "avg_duration": statistics.mean(val['durations']),
                    "avg_steps": statistics.mean(val['steps'])
                }
        return report

    def generate_markdown(self) -> str:
        metrics = self.compute_metrics()
        
        md = "# Benchmark Report\n\n"
        md += "| Scenario | Strategy | Runs | Success Rate | Avg Time (s) | Avg Steps |\n"
        md += "|---|---|---|---|---|---|\n"
        
        for key, m in metrics.items():
            scenario, strategy = key.split('_', 1)
            md += f"| {scenario} | {strategy} | {m['total_runs']} | {m['success_rate']:.1%} | {m['avg_duration']:.2f} | {m['avg_steps']:.1f} |\n"
            
        return md
