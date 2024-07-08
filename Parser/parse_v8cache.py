
import subprocess
import os
from Parser.sfi_file_parser import parse_file


def get_version(view8_dir, file_name):
    # Define the relative path to the binary
    binary_path = os.path.join(view8_dir, 'Bin', 'VersionDetector.exe')

    # Ensure the binary exists
    if not os.path.isfile(binary_path):
        raise FileNotFoundError(f"The binary '{binary_path}' does not exist.")

    # Call the binary with the file name as argument
    try:
        result = subprocess.run([binary_path, '-f', file_name], capture_output=True, text=True, check=True)
        # Return the output from the binary
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to detect version for file {file_name}.")


def run_disassembler_binary(binary_path, file_name, out_file_name):
    # Ensure the binary exists
    if not os.path.isfile(binary_path):
        raise FileNotFoundError(
            f"The binary '{binary_path}' does not exist. "
            "You can specify a path to a similar disassembler version using the --path (-p) argument."
        )

    # Open the output file in write mode
    with open(out_file_name, 'w') as outfile:
        # Call the binary with the file name as argument and pipe the output to the file
        try:
            result = subprocess.run([binary_path, file_name], stdout=outfile, stderr=subprocess.PIPE, text=True)

            # Check the return status code
            if result.stderr:
                raise RuntimeError(
                    f"Binary execution failed with status code {result.returncode}: {result.stderr.strip()}")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Error calling the binary: {e}")


def parse_v8cache_file(file_name, out_name, view8_dir, binary_path):
    if not binary_path:
        print(f"Detecting version.")
        version = get_version(view8_dir, file_name)
        print(f"Detected version: {version}.")
        # Define the binary name using the version
        binary_name = f"{version}.exe"
        binary_path = os.path.join(view8_dir, 'Bin', binary_name)
    print(f"Executing disassembler binary: {binary_path}.")
    run_disassembler_binary(binary_path, file_name, out_name)
    print(f"Disassembly completed successfully.")


def parse_disassembled_file(out_name):
    print(f"Parsing disassembled file.")
    all_func = parse_file(out_name)
    print(f"Parsing completed successfully.")
    return all_func
