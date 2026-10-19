"""Read-only format bridges for saved public traces; never runs an agent/model."""
import argparse
import json
from pathlib import Path


def atif(trace):
    """ATIF-v1.7 message export with separate role/request subtrajectories.

    This exports recorded messages, not an implementation of Harbor execution.
    No fabricated thinking or grader answer is placed in an agent message.
    """
    meta = trace['meta']
    children = []
    for i, request in enumerate(trace.get('requests', []), 1):
        steps = []
        for message in request['request'].get('messages', []):
            role = message.get('role', 'user')
            source = 'agent' if role == 'assistant' else role if role in ('system', 'user') else 'user'
            content = message.get('content', '')
            steps.append({'step_id': len(steps)+1, 'source': source,
                'message': content if isinstance(content, str) else json.dumps(content, ensure_ascii=False),
                'extra': {'recorded_message_role': role}})
        decision = request.get('decision', {})
        if 'raw_response' in decision:
            steps.append({'step_id': len(steps)+1, 'source': 'agent',
                          'message': json.dumps(decision['raw_response'], ensure_ascii=False)})
        children.append({'schema_version': 'ATIF-v1.7', 'trajectory_id': meta['id']+f'-request-{i}',
            'agent': {'name': request.get('role') or 'recorded-role', 'version': 'recorded-public-v1',
                      'model_name': decision.get('model_id') or decision.get('requested_model') or meta['model']},
            'steps': steps, 'extra': {'role_kind': request.get('role_kind'),
                                    'source_request_sha256': request.get('source_request_sha256')}})
    return {'schema_version': 'ATIF-v1.7', 'trajectory_id': meta['id'], 'session_id': meta['id'],
            'agent': {'name': 'redcommerce-recorded-session', 'version': 'public-v1'},
            'steps': [{'step_id': 1, 'source': 'user', 'message': trace['task']['instruction']}],
            'subagent_trajectories': children,
            'extra': {'export_kind': 'saved-message interchange; not a Harbor execution',
                      'original_meta': meta, 'outcome_record': trace['outcome_record'],
                      'source_provenance': trace['provenance'],
                      'private_reasoning_exported': False}}


def inspect_sample(trace, filename):
    return {'id': trace['meta']['id'], 'input': trace['task']['instruction'], 'target': '',
            'metadata': {'trajectory_file': str(filename), 'recorded_meta': trace['meta'],
                         'recorded_outcome': trace['outcome_record'],
                         'mode': 'saved-trajectory import; not a new model evaluation'}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('trace', type=Path)
    parser.add_argument('--format', choices=['atif', 'inspect-jsonl'], required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--validate-harbor', action='store_true', help='Requires a separately installed Harbor package')
    args = parser.parse_args()
    trace = json.loads(args.trace.read_text('utf-8'))
    result = atif(trace) if args.format == 'atif' else inspect_sample(trace, args.trace.name)
    if args.validate_harbor:
        if args.format != 'atif':
            raise ValueError('Harbor validation is only applicable to ATIF')
        from harbor.models.trajectories import Trajectory
        Trajectory.model_validate(result)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2 if args.format == 'atif' else None)+'\n', 'utf-8')
    print('Saved-message export complete; no model calls. ' + str(args.out))


if __name__ == '__main__':
    main()
