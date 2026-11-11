import json
import re
import logging
import sys

logger = logging.getLogger("openhands.evaluation")

def check_coverage(coverage_output, code_file):
    """
    Parses coverage output. 
    1. Tries to clean and parse JSON.
    2. Uses Regex fallback if JSON fails.
    """
    def debug_print(msg):
        print(f"[check_coverage DEBUG] {msg}", file=sys.stderr)

    debug_print(f"Checking coverage for: '{code_file}'")
    
    clean_output = coverage_output.replace('\n', '').replace('\r', '').strip()
    
    if not clean_output:
        debug_print("Empty output.")
        return False, 0

    percent = None
    
    try:
        start = clean_output.find('{')
        end = clean_output.rfind('}')
        
        json_str = clean_output
        if start != -1 and end != -1:
            json_str = clean_output[start:end+1]
            
        data = json.loads(json_str, strict=False)
        debug_print("JSON parsed successfully.")
        
        files_data = data.get('files', {})
        
        target_norm = code_file.strip()
        if target_norm.startswith('/testbed/'): target_norm = target_norm[9:]
        target_norm = target_norm.lstrip('./').lstrip('/')
        
        debug_print(f"Normalized target: {target_norm}")
        debug_print(f"Available keys: {list(files_data.keys())}")

        for key, file_obj in files_data.items():
            key_norm = key.strip()
            if key_norm.startswith('/testbed/'): key_norm = key_norm[9:]
            key_norm = key_norm.lstrip('./').lstrip('/')
            
            if key_norm.endswith(target_norm) or target_norm.endswith(key_norm) or target_norm in key_norm or key_norm in target_norm:
                debug_print(f"Match found: {key}")
                success, val = _extract_percent(file_obj)
                if success:
                    return True, val
    except Exception as e:
        debug_print(f"JSON parsing/matching failed: {e}")

    debug_print("Attempting Regex fallback...")
    try:
        
        simple_name = code_file.split('/')[-1]
        
        pattern = re.compile(re.escape(simple_name) + r'.*?"percent_covered"\s*:\s*([\d\.]+)', re.IGNORECASE)
        
        match = pattern.search(clean_output)
        if match:
            val = float(match.group(1))
            debug_print(f"Regex match found: {val}")
            return True, val
            
        debug_print("Specific file regex failed. Looking for any file summary...")
        pattern_fallback = re.compile(r'"summary".*?"percent_covered"\s*:\s*([\d\.]+)')
        match_fb = pattern_fallback.search(clean_output)
        if match_fb:
             val = float(match_fb.group(1))
             debug_print(f"Fallback regex found: {val}")
             return True, val

    except Exception as e:
        debug_print(f"Regex failed: {e}")

    debug_print("All methods failed.")
    return False, 0


def _extract_percent(file_data):
    try:
        summary = file_data.get('summary', {})
        percent = summary.get('percent_covered')
        if percent is None:
            percent = summary.get('percent_covered_display')
        if percent is not None:
            return True, float(percent)
        return False, 0
    except:
        return False, 0


def check_mutation(mutation_output):
    if 'total jobs: ' in mutation_output:
        try:
            lines = mutation_output.splitlines()
            job_line = next((line for line in lines if 'total jobs: ' in line), None)
            num_mutants = int(job_line.split('total jobs: ')[1].split()[0]) if job_line else -1

            final_conf = lines[-1].strip() or lines[-2].strip()
            parts = final_conf.split()
            if len(parts) >= 3:
                val = float(parts[1])
                high = float(parts[2])
                return True, num_mutants, 100 - val, high - val
        except:
            pass
    return False, -1, 0, -1


def count_methods(code_str):
    if not code_str: return 0
    pattern = r'\bdef\b\s+\w+\s*\('
    return len(re.findall(pattern, code_str))


def get_lines_of_code(code_str):
    if not code_str: return 0
    return len(code_str.strip().split('\n'))