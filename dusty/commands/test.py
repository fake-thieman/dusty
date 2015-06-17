import os
import sys
import textwrap
from prettytable import PrettyTable

from .. import constants
from ..compiler.spec_assembler import get_expanded_libs_specs, get_all_repos_for_app_or_library
from ..compiler.compose import get_volume_mounts, get_testing_compose_dict, container_code_path
from ..systems.docker.testing_image import ensure_test_image, test_image_name
from ..systems.docker import get_docker_client
from ..systems.docker.compose import write_composefile, compose_up
from ..systems.rsync import sync_repos_by_specs
from ..systems.virtualbox import initialize_docker_vm
from ..log import log_to_client

def test_info_for_app_or_lib(app_or_lib_name):
    expanded_specs = get_expanded_libs_specs()
    spec = expanded_specs.get_app_or_lib(app_or_lib_name)
    if not spec['test']['suites']:
        log_to_client('No test suite registered for {}'.format(app_or_lib_name))
        return

    table = PrettyTable(['Test Suite', 'Description', 'Default Args'])
    for suite_spec in spec['test']['suites']:
        table.add_row([suite_spec['name'],
                       '\n'.join(textwrap.wrap(suite_spec['description'], 80)),
                       suite_spec['default_args']])
    log_to_client(table.get_string(sortby='Test Suite'))

def run_app_or_lib_tests(app_or_lib_name, suite_name, test_arguments, force_recreate=False, pull_repos=True):
    log_to_client("Ensuring virtualbox vm is running")
    initialize_docker_vm()
    client = get_docker_client()
    expanded_specs = get_expanded_libs_specs()
    spec = expanded_specs.get_app_or_lib(app_or_lib_name)
    if pull_repos:
        for repo in get_all_repos_for_app_or_library(app_or_lib_name):
            import logging
            logging.error(repo.remote_path)
            repo.update_local_repo()
    sync_repos_by_specs([spec])
    test_command = _construct_test_command(spec, suite_name, test_arguments)
    ensure_test_image(client, app_or_lib_name, expanded_specs, force_recreate=force_recreate)
    _run_tests_with_image(client, expanded_specs, app_or_lib_name, test_command)

def _construct_test_command(spec, suite_name, test_arguments):
    suite_command = None
    for suite_dict in spec['test']['suites']:
        if suite_dict['name'] == suite_name:
            suite_command = suite_dict['command']
            suite_default_args = suite_dict['default_args']
            break
    if suite_command is None:
        raise RuntimeError('{} is not a valid suite name'.format(suite_name))
    if not test_arguments:
        test_arguments = suite_default_args.split(' ')
    cd_command = 'cd {}'.format(container_code_path(spec))
    sub_command = "{} {}".format(suite_command, ' '.join(test_arguments))
    test_command = 'sh -c "{}; {}"'.format(cd_command, sub_command.strip())
    log_to_client('Command to run in test is {}'.format(test_command))
    return test_command

def _test_composefile_path(service_name):
    return os.path.expanduser('~/.dusty-testing/test_{}.yml'.format(service_name))

def _compose_project_name(service_name):
    return 'test{}'.format(service_name.lower())

def _services_compose_up(expanded_specs, app_or_lib_name, testing_spec):
    previous_container_names = []
    for service_name in testing_spec['services']:
        service_spec = expanded_specs['services'][service_name]
        kwargs = {}
        if previous_container_names:
            kwargs['net_container_identifier'] = previous_container_names[-1]
        service_compose_config = get_testing_compose_dict(service_name, service_spec, **kwargs)

        composefile_path = _test_composefile_path(service_name)
        write_composefile(service_compose_config, composefile_path)
        log_to_client('Compose config {}: \n {}'.format(service_name, service_compose_config))

        compose_up(composefile_path, _compose_project_name(app_or_lib_name))
        previous_container_names.append("{}_{}_1".format(_compose_project_name(app_or_lib_name), service_name))
    return previous_container_names

def _app_or_lib_compose_up(testing_spec, app_or_lib_name, app_or_lib_volumes, test_command, previous_container_name):
    image_name = test_image_name(app_or_lib_name)
    kwargs = {'testing_image_identifier': image_name,
              'volumes': app_or_lib_volumes,
              'command': test_command}

    if previous_container_name is not None:
        kwargs['net_container_identifier'] = previous_container_name
    composefile_path = _test_composefile_path(app_or_lib_name)
    compose_config = get_testing_compose_dict(app_or_lib_name, testing_spec.get('compose', {}), **kwargs)
    write_composefile(compose_config, composefile_path)
    compose_up(composefile_path, _compose_project_name(app_or_lib_name))
    return '{}_{}_1'.format(_compose_project_name(app_or_lib_name), app_or_lib_name)

def _run_tests_with_image(client, expanded_specs, app_or_lib_name, test_command):
    testing_spec = expanded_specs.get_app_or_lib(app_or_lib_name)['test']

    volumes = get_volume_mounts(app_or_lib_name, expanded_specs)
    previous_container_names = _services_compose_up(expanded_specs, app_or_lib_name, testing_spec)
    previous_container_name = previous_container_names[-1] if previous_container_names else None
    test_container_name = _app_or_lib_compose_up(testing_spec, app_or_lib_name,
                                                 volumes, test_command, previous_container_name)

    for line in client.logs(test_container_name, stdout=True, stderr=True, stream=True):
        log_to_client(line.strip())
    exit_code = client.wait(test_container_name)
    client.remove_container(container=test_container_name)

    for service_container in previous_container_names:
        log_to_client('Stopping service container {}'.format(service_container))
        try:
            client.stop(service_container, timeout=1)
        except Exception:
            log_to_client('Exception stopping service container {}'.format(service_container))

    log_to_client('TESTS {}'.format('FAILED' if exit_code != 0 else 'PASSED'))
    sys.exit(exit_code)
