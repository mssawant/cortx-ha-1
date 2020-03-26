import argparse
import json
import os
import sys
import logging
from typing import List

from pcswrap.exception import CliException, MaintenanceFailed, TimeoutException
from pcswrap.internal.connector import CliConnector
from pcswrap.types import Resource, Node, PcsConnector
from pcswrap.internal.waiter import Waiter

__all__ = ['Client', 'main']


def all_stopped(resource_list: List[Resource]) -> bool:
    logging.debug('The following resources are found: %s', resource_list)
    return all([not r.active for r in resource_list])


def non_standby_nodes(node_list: List[Node]) -> bool:
    logging.debug('The following nodes are found: %s', node_list)
    return all([not n.standby for n in node_list])


class Client():
    def __init__(self, connector: PcsConnector = None):
        self.connector: PcsConnector = connector or CliConnector()
        self._ensure_sane()

    def _ensure_sane(self) -> None:
        self.connector.get_nodes()

    def get_all_nodes(self) -> List[Node]:
        return self.connector.get_nodes()

    def get_online_nodes(self) -> List[Node]:
        return [x for x in self.connector.get_nodes() if x.online]

    def unstandby_node(self, node_name) -> None:
        self.connector.unstandby_node(node_name)

    def standby_node(self, node_name) -> None:
        self.connector.standby_node(node_name)

    def get_cluster_name(self) -> str:
        return self.connector.get_cluster_name()

    def standby_all(self, timeout: int = 120) -> None:
        self.connector.standby_all()
        waiter = Waiter(title='no running resources',
                        timeout_seconds=timeout,
                        provider_fn=self.connector.get_resources,
                        predicate=all_stopped)
        waiter.wait()

    def unstandby_all(self, timeout: int = 120) -> None:
        self.connector.unstandby_all()
        waiter = Waiter(title='no standby nodes in cluster',
                        timeout_seconds=timeout,
                        provider_fn=self.connector.get_nodes,
                        predicate=non_standby_nodes)
        waiter.wait()

    def shutdown_node(self, node_name: str) -> None:
        self.connector.shutdown_node(node_name)

    def disable_stonith(self, timeout: int = 120) -> None:
        resources = self.connector.get_stonith_resources()
        for r in resources:
            self.connector.disable_resource(r)

        waiter = Waiter(title='stonith resources are disabled',
                        timeout_seconds=timeout,
                        provider_fn=self.connector.get_stonith_resources,
                        predicate=all_stopped)
        waiter.wait()

    def enable_stonith(self, timeout: int = 120) -> None:
        resources = self.connector.get_stonith_resources()
        for r in resources:
            self.connector.enable_resource(r)

        def all_started(resource_list: List[Resource]) -> bool:
            logging.debug('The following resources are found: %s',
                          resource_list)
            return all([r.active for r in resource_list])

        waiter = Waiter(title='stonith resources are enabled',
                        timeout_seconds=timeout,
                        provider_fn=self.connector.get_stonith_resources,
                        predicate=all_started)
        waiter.wait()


def parse_opts(argv: List[str]):
    prog_name = os.environ.get('PCSCLI_PROG_NAME')

    p = argparse.ArgumentParser(prog=prog_name,
                                description='Manages the nodes in HA cluster.')
    p.add_argument('--verbose',
                   help='Be verbose while executing',
                   action='store_true',
                   default=False,
                   dest='verbose')

    subparsers = p.add_subparsers()
    status_parser = subparsers.add_parser(
        'status',
        help='Show status of all cluster nodes',
    )
    unstandby_parser = subparsers.add_parser('unstandby',
                                             help='Unstandby a node')
    standby_parser = subparsers.add_parser('standby', help='Standby a node')
    shutdown_parser = subparsers.add_parser(
        'shutdown', help='Shutdown (power off) the node by name')

    standby_parser.add_argument('standby_node',
                                type=str,
                                nargs='?',
                                help='Name of the node to standby')
    standby_parser.add_argument(
        '--all',
        action='store_true',
        dest='standby_node_all',
        help='Standby all the nodes in the cluster (no node name is required)')
    unstandby_parser.add_argument('unstandby_node',
                                  type=str,
                                  nargs='?',
                                  help='Name of the node to unstandby')
    unstandby_parser.add_argument(
        '--all',
        action='store_true',
        dest='unstandby_node_all',
        help='Unstandby all the nodes in the cluster '
        '(no node name is required)')
    status_parser.add_argument('--stub',
                               dest='show_status',
                               default=True,
                               help=argparse.SUPPRESS)
    shutdown_parser.add_argument('shutdown_node',
                                 type=str,
                                 nargs=1,
                                 help='Name of the node to poweroff')
    maintenance_parser = subparsers.add_parser(
        'maintenance',
        help='Switch the cluster to maintenance mode',
    )
    maintenance_parser.add_argument('--all',
                                    dest='maintenance_all',
                                    action='store_true')

    maintenance_parser.add_argument(
        '--timeout-sec',
        type=int,
        dest='timeout_sec',
        default=120,
        help='Maximum time that this command will'
        ' wait for any operation to complete before raising an error')

    unmaintenance_parser = subparsers.add_parser(
        'unmaintenance',
        help='Move the cluster from maintenance back to normal mode',
    )
    unmaintenance_parser.add_argument('--all',
                                      dest='unmaintenance_all',
                                      action='store_true')

    unmaintenance_parser.add_argument(
        '--timeout-sec',
        type=int,
        dest='timeout_sec',
        default=120,
        help='Maximum time that this command will'
        ' wait for any operation to complete before raising an error')
    opts = p.parse_args(argv)
    return opts


def _get_client() -> Client:
    return Client()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level,
                        stream=sys.stderr,
                        format='%(asctime)s [%(levelname)s] %(message)s')


def _cluster_maintenance(timeout: int = 120):
    client = Client()
    logging.info('Disabling stonith resources first')

    try:
        client.disable_stonith(timeout)
    except TimeoutException:
        raise MaintenanceFailed()
    logging.debug('Switching to standby mode')
    try:
        client.standby_all(timeout)
    except Exception:
        raise MaintenanceFailed()

    logging.info('All nodes are in standby mode now')


def _cluster_unmaintenance(timeout: int = 120):
    client = Client()
    client.unstandby_all(timeout=timeout)
    logging.info('All nodes are back to normal mode.')
    client.enable_stonith(timeout=timeout)
    logging.info('Stonith resources are enabled. Cluster is functional now.')


def _run(args) -> None:
    is_verbose = args.verbose
    _setup_logging(is_verbose)

    if hasattr(args, 'standby_node'):
        if hasattr(args, 'standby_node_all'):
            _get_client().standby_all()
        else:
            _get_client().standby_node(args.standby_node)
    elif hasattr(args, 'unstandby_node'):
        if hasattr(args, 'unstandby_node_all'):
            _get_client().unstandby_all()
        else:
            _get_client().unstandby_node(args.stop_node)
    elif hasattr(args, 'show_status'):
        nodes = [node._asdict() for node in _get_client().get_all_nodes()]
        json_str = json.dumps(nodes)
        print(json_str)
    elif hasattr(args, 'shutdown_node'):
        node = args.shutdown_node[0]
        _get_client().shutdown_node(node)
    elif hasattr(args, 'maintenance_all'):
        _cluster_maintenance(timeout=args.timeout_sec)
    elif hasattr(args, 'unmaintenance_all'):
        _cluster_unmaintenance(timeout=args.timeout_sec)


def main() -> None:
    args = parse_opts(sys.argv[1:])
    try:
        _run(args)
    except MaintenanceFailed:
        logging.error('Failed to switch to maintenance mode.')
        logging.error(
            'The cluster is now unstable. Maintenance mode '
            'was not rolled back to prevent STONITH actions to happen '
            'unexpectedly.')
        prog_name = os.environ.get('PCSCLI_PROG_NAME') or 'pcswrap'
        logging.error(
            'Consider running `%s unmaintenance --all` to switch'
            ' the cluster to normal mode manually.', prog_name)
        sys.exit(1)

    except CliException as e:
        logging.error('Exiting with FAILURE: %s', e)
        logging.debug('Detailed info', exc_info=True)
        sys.exit(1)
    except Exception:
        logging.exception('Unexpected error happened')
        sys.exit(1)
