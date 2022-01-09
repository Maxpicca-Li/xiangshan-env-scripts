import argparse
import csv
import os
import sys
import time

sys.path.append('../perf')
import perf

from github import Github


def get_commit_messages(token, sha):
    g = Github(token)
    xs = g.get_repo("OpenXiangShan/XiangShan")
    return list(map(lambda s: xs.get_commit(s).commit.message.splitlines()[0], sha))

def get_recent_commits(token, number=10):
    g = Github(token)
    xs = g.get_repo("OpenXiangShan/XiangShan")
    actions = xs.get_workflow_runs(branch="master")
    recent_commits = list(map(lambda a: a.head_sha, actions[:number]))
    run_numbers = list(map(lambda a: a.run_number, actions[:number]))
    commit_messages = get_commit_messages(token, recent_commits)
    return run_numbers, recent_commits, commit_messages

def write_to_csv(rows, filename):
    with open(filename, 'w') as csvfile:
        csvwriter = csv.writer(csvfile)
        csvwriter.writerows(rows)

def get_all_manip():
    all_manip = []
    ipc = perf.PerfManip(
        name = "global.IPC",
        counters = [f"clock_cycle",
        f"commitInstr"],
        func = lambda cycle, instr: instr * 1.0 / cycle
    )
    all_manip.append(ipc)
    return all_manip

def get_actions_data(run_numbers, commits, messages):
    assert(len(run_numbers) == len(commits))
    with_message = messages is not None
    base_dir = "/bigdata/xs-perf"
    results = {}
    benchmarks = []
    for i, (run_number, commit) in enumerate(zip(run_numbers, commits)):
        perf_path = os.path.join(base_dir, str(run_number))
        if not os.path.isdir(perf_path):
            print(f"{commit} perf data {perf_path} not found. Skip.")
            continue
        print(commit, perf_path)
        results[commit] = {}
        for filename in os.listdir(perf_path):
            if filename.endswith(".log"):
                benchmark = filename[:-4]
                counters = perf.PerfCounters(os.path.join(perf_path, filename))
                counters.add_manip(get_all_manip())
                benchmarks.append(benchmark)
                results[commit][benchmark] = "{:.3f}".format(float(counters["global.IPC"]))
                if with_message:
                    results[commit]["message"] = messages[i]
    benchmarks = sorted(list(set(benchmarks)))
    if with_message:
        benchmarks = ["message"] + benchmarks
    all_rows = [["commit"] + benchmarks]
    for i, commit in enumerate(results):
        all_rows.append([commit[:7]] + [results.get(commit, dict()).get(bench, "") for bench in benchmarks])
    return all_rows

def has_robot(comments, commit):
    for comment in comments:
        find_robot_head = comment.find("[Generated by IPC robot]") != -1
        find_commit = comment.find(f"commit: {commit}") != -1
        if find_robot_head and find_commit:
            return True
    return False

def prepare_comment(token, commit_sha, number):
    data = get_actions_data([number], [commit_sha], None)
    if len(data[0]) - 2 > 0:
        print(f"Generate comment for {commit_sha} ...")
        comment = ["[Generated by IPC robot]"]
        comment.append(f"commit: {commit_sha}")
        table_rows = csv_to_markdown_table(data)
        comment += table_rows
        comment.append("")
        comment.append(f"master branch:")
        master_data = get_master_commits(token, with_message=False)
        comment += csv_to_markdown_table(master_data)
        return True, "\n".join(comment)
    return False, ""

def csv_to_markdown_table(csv_rows):
    tables_rows = list(map(lambda row: "| " + " | ".join(row) + " |", csv_rows))
    columns = len(csv_rows[0])
    align_row = "| :---: " * columns + " |"
    return [tables_rows[0], align_row] + tables_rows[1:]

def get_master_commits(token, number=10, with_message=True):
    run_numbers, commits, messages = get_recent_commits(token, number)
    all_rows = get_actions_data(run_numbers, commits, messages if with_message else None)
    return all_rows

def get_pull_requests(token):
    g = Github(token)
    xs = g.get_repo("OpenXiangShan/XiangShan")
    actions = xs.get_workflow_runs(event="pull_request", status="success")
    for action in actions[:15]:
        if not action.pull_requests:
            continue
        pull_request = action.pull_requests[0]
        all_comments = list(map(lambda c: c.body, pull_request.get_issue_comments()))
        if not has_robot(all_comments, action.head_sha):
            success, comment = prepare_comment(token, action.head_sha, action.run_number)
            if success:
                print(f"Create comment at {pull_request.html_url}:")
                print(comment)
                pull_request.create_issue_comment(comment)
            else:
                print(f"perf data not found for {pull_request.html_url} {action.head_sha}")
                print(action.run_number, action.head_branch)
        else:
            print(f"{pull_request.html_url} {action.head_sha} has been commented")

def main(token, output_csv, number, always_on):
    error_count = 0
    while always_on:
        try:
            get_pull_requests(token)
        except KeyboardInterrupt:
            sys.exit()
        except:
            error_count += 1
            print(f"ERROR count {error_count}!!!!")
        else:
            # check PRs every 5 minutes
            time.sleep(300)
    run_numbers, commits, messages = get_recent_commits(token, number)
    all_rows = get_actions_data(run_numbers, commits, messages)
    write_to_csv(all_rows, output_csv)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='stargazers analysis')
    parser.add_argument('--token', '-t', default=None, help='github token')
    parser.add_argument('--output', '-o', default="actions.csv", help='output csv file')
    parser.add_argument('--number', '-n', default=20, type=int, help='number of commits')
    parser.add_argument('--always-on', '-a', default=False, action="store_true", help='always check PRs')

    args = parser.parse_args()

    main(args.token, args.output, args.number, args.always_on)

