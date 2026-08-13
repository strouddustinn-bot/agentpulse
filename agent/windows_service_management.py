import subprocess
import os
import sys
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def check_services_windows(services):
    results = []
    for service in services:
        logging.info(f"Checking status of service: {service}")
        command = f"sc query {service}"
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if "RUNNING" in result.stdout:
            logging.info(f"Service {service} is running.")
            results.append({'service': service, 'breached': False})
        else:
            logging.error(f"Service {service} failed or is not running.")
            results.append({'service': service, 'breached': True, 'reason': result.stdout})
    return results


def cleanup_disk_windows(paths):
    logging.info(f"Cleaning up disk paths: {paths}")
    for path in paths:
        command = f"del {path}"
        result = subprocess.run(command, shell=True)
        if result.returncode == 0:
            logging.info(f"Successfully cleaned up {path}.")
        else:
            logging.error(f"Failed to clean up {path}. Return code: {result.returncode}")
