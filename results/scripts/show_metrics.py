#!/usr/bin/env python3
import json
import sys


def show_metrics(file_path):
    coverages = []
    branch_coverages = []
    mutations = []
    any_pass_count = 0
    all_pass_count = 0
    total = 0

    with open(file_path, 'r') as f:
        for line in f:
            data = json.loads(line)
            report = data.get('test_result', {}).get('report', {})
            total += 1

            coverages.append(report.get('coverage', 0))
            branch_coverages.append(report.get('reb_branch_coverage', 0))
            mutations.append(report.get('mutation_score', 0))

            if report.get('tests_pass', False):
                any_pass_count += 1
            if report.get('all_tests_pass', False):
                all_pass_count += 1

    print(f"Coverage: {sum(coverages)/len(coverages):.2f}%")
    print(f"Branch Coverage: {sum(branch_coverages)/len(branch_coverages):.2f}%")
    print(f"Mutation: {sum(mutations)/len(mutations):.2f}%")
    print(f"Any Pass@1: {any_pass_count/total*100:.2f}% ({any_pass_count}/{total})")
    print(f"All Pass@1: {all_pass_count/total*100:.2f}% ({all_pass_count}/{total})")


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <jsonl_file_path>")
        sys.exit(1)
    show_metrics(sys.argv[1])
