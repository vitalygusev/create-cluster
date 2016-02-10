from ConfigParser import SafeConfigParser
import json
from sys import argv
import time
import urllib2

from componentshttp import logger
import nailgun_client as fuel


def create_cluster(fuel_ip, kvm_count, machines_count, cluster_settings):

    #   Connect to Fuel Main Server

    client = fuel.NailgunClient(str(fuel_ip))

    #   Clean Fuel cluster

    for cluster in client.list_clusters():
        client.delete_cluster(cluster['id'])
        while True:
            try:
                client.get_cluster(cluster['id'])
            except urllib2.HTTPError as e:
                if str(e) == "HTTP Error 404: Not Found":
                    break
                else:
                    raise
            except Exception:
                raise
            time.sleep(1)

    #   Create cluster

    get_release = lambda x: next(release['id'] for release
                                 in client.get_releases()
                                 if release['operating_system'].lower() == x)

    release_id = get_release(cluster_settings['release_name'])

    data = {"name": cluster_settings['env_name'],
            "release": release_id,
            "mode": cluster_settings['config_mode'],
            "net_provider": cluster_settings['net_provider']}
    if cluster_settings.get('net_segment_type'):
        data['net_segment_type'] = cluster_settings['net_segment_type']

    client.create_cluster(data)

    #   Update cluster configuration

    cluster_id = client.get_cluster_id(cluster_settings['env_name'])
    attributes = client.get_cluster_attributes(cluster_id)

    settings = json.loads(cluster_settings['settings'])

    for option in settings:
        section = False
        if option in ('sahara', 'murano', 'ceilometer'):
            section = 'additional_components'
        if option in ('volumes_ceph', 'images_ceph', 'ephemeral_ceph',
                      'objects_ceph', 'osd_pool_size', 'volumes_lvm'):
            section = 'storage'
        if option in ('method'):
            section = 'provision'
        if section:
            attributes['editable'][section][option]['value'] = settings[option]

    plugins = json.loads(cluster_settings['plugins'])

    for i in plugins.keys():
        attributes['editable'][i]['metadata']['enabled'] = True
        for key, value in plugins[i].iteritems():
            attributes['editable'][i]['metadata'][
                'versions'][0][key]['value'] = value

    hpv_data = attributes['editable']['common']['libvirt_type']
    hpv_data['value'] = str(cluster_settings['virt_type'])

    debug = cluster_settings.get('debug', 'false')
    auto_assign = cluster_settings.get('auto_assign_floating_ip', 'false')
    nova_quota = cluster_settings.get('nova_quota', 'false')

    attributes['editable']['common']['debug']['value'] = json.loads(debug)
    attributes['editable']['common'][
        'auto_assign_floating_ip']['value'] = json.loads(auto_assign)
    attributes['editable']['common']['nova_quota']['value'] = \
        json.loads(nova_quota)

    if 'public_ssl' in attributes['editable']:
        # SSL/TLS for public services endpoints
        public_ssl = cluster_settings.get('public_ssl', 'false').lower()
        attributes['editable']['public_ssl']['services']['value'] = \
            public_ssl == 'true'
        # SSL/TLS for Horizon
        horizon_ssl = cluster_settings.get('horizon_ssl', 'false').lower()
        attributes['editable']['public_ssl']['horizon']['value'] = \
            horizon_ssl == 'true'

    client.update_cluster_attributes(cluster_id, attributes)

    #  Loop for wait cluster nodes

    counter = 0
    while True:

        actual_kvm_count = len([k for k in client.list_nodes()
                                if not k['cluster'] and k['online']
                                and k['status'] == 'discover'
                                and k['manufacturer'] in ['KVM', 'QEMU']])

        actual_machines_count = len([k for k in client.list_nodes()
                                    if not k['cluster'] and k['online']
                                    and k['status'] == 'discover'
                                    and k['manufacturer'] == 'Supermicro'])

        if (actual_kvm_count >= int(kvm_count)
                and actual_machines_count >= int(machines_count)):
            break
        counter += 5
        if counter > 60 * 15:
            raise RuntimeError
        time.sleep(5)

    #   Network configuration on environment

    default_networks = client.get_networks(cluster_id)

    networks = json.loads(cluster_settings['networks'])

    change_dict = networks.get('networking_parameters', {})
    for key, value in change_dict.items():
        default_networks['networking_parameters'][key] = value

    for net in default_networks['networks']:
        change_dict = networks.get(net['name'], {})
        for key, value in change_dict.items():
            net[key] = value

    client.update_network(cluster_id,
                          default_networks['networking_parameters'],
                          default_networks['networks'])

    #   Loop with operations of nodes

    for node_name, params in json.loads(
            cluster_settings['node_roles']).items():

        #   Add all available nodes to cluster

        if 'version' in params:
            node = next(k for k in client.list_nodes()
                        if k['platform_name'] == node_name
                        and k['manufacturer'] == params['manufacturer']
                        and not k['cluster'] and k['online'])
        else:
            node = next(k for k in client.list_nodes()
                        if k['manufacturer'] == params['manufacturer']
                        and not k['cluster'] and k['online'])

        data = {"cluster": str(cluster_id),
                "pending_roles": params['roles'],
                "pending_addition": True,
                "name": node_name}

        client.update_node(node['id'], data)

if __name__ == "__main__":
    parser = SafeConfigParser()
    parser.read(argv[1])

    cluster_settings = dict(parser.items('cluster'))
    fuel_ip = json.loads(cluster_settings['fuel_ip'])
    kvm_count = json.loads(cluster_settings['kvm_count'])
    machines_count = json.loads(cluster_settings['machines_count'])

    create_cluster(fuel_ip, kvm_count, machines_count, cluster_settings)

