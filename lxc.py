from fabric.api import env, run, local, hosts, execute, task
from time import sleep

env.password = 'root'

@task
def setup_lxc(name, ip, gateway, dns, mac, vif, public_key, distro="natty", reset=False):
    """
    Starts a standard lxc template, and set it up to a runnable server (idempotent)

    Arguments:
    name -- the name of the container (example : toto)
    ip   -- the ip of the container on the virtual network (example : 10.0.42.2)
    gateway -- the ip of your controler, on the virtuall network (example : 10.0.42.1)
    dns -- the ip of the nameserver, as seen from the virtual network (example : 10.0.42.1)
    mac -- any virtual mac addresse for you virtual device (example : 00:00:00:00:01)
    vif -- the name of the virtual device, as seen form the controler (example : veth1)
    public_key -- the path to the public key to authenticate fabric on the host  (example : ~/.ssh/id_rsa)
    distro -- name of the lxc template (example : natty)
    reset -- True if you want to set up from scratch

    """

    if (reset and exists_lxc(name)): clean_lxc(name)
    if (exists_lxc(name)): return

    # network setup
    conf = """
lxc.network.type=veth
lxc.network.link=br0
lxc.network.flags=up
lxc.network.ipv4=%s/24
lxc.network.hwaddr=%s
lxc.network.veth.pair=%s
"""  % (ip, mac, vif)
    create_local_file(conf,"/tmp/lxc.conf")
    local_sudo('lxc-create -n %s -t %s -f /tmp/lxc.conf' % (name, distro))
    interfaces = """
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
  address %s
  netmask 255.255.255.0
  network 192.168.42.0
#  gateway %s
""" % (ip, gateway)
    create_file_in_lxc(interfaces,'/etc/network/interfaces',name)
    create_file_in_lxc('route add default gw %s \n exit 0' % gateway, '/etc/rc.local',name)
    create_file_in_lxc('nameserver %s' %dns, '/etc/resolvconf/resolv.conf.d/base',name)

    # disable apt cache (cache on the container side with a tranparent proxy)
    create_file_in_lxc('APT::Archves::MaxSize "0";','/etc/apt/apt.conf.d/20archives',name) 

    # install public key for root 
    create_dir_in_lxc('/root/.ssh', name)
    key = local('cat %s' % public_key, capture = True)
    create_file_in_lxc(key, '/root/.ssh/authorized_keys', name)

    # start the constainer
    local_sudo('lxc-start -d -n %s' % name)
    local_sudo('lxc-wait -n %s -s RUNNING' % name)
    sleep(3)

    # connect via ssh, disable password and install sudo
    execute(disable_root_password,  host= 'root@%s' % ip)
    execute(install_sudo,  host= 'root@%s' % ip)

@task
def clean_lxc(name):
    """
    destroy a lxc container (idempotent)
    """
    local_sudo('lxc-stop -n %s' % name)
    if exists_lxc(name) : local_sudo('lxc-destroy -n %s' % name)

def exists_lxc(name):
    """
    check if the named lxc container exists
    """
    return local('ls /var/lib/lxc/', capture = True).find(name) >= 0

def install_sudo():
    run('apt-get -y --allow-unauthenticated -y install sudo')

def disable_root_password():
    run('passwd --lock root')

def create_local_file(content,path):
    local("echo '%s' > %s" % (content, path))

def create_file_in_lxc(content,path,name):
    fullpath = '/var/lib/lxc/%s/rootfs/%s' % (name, path)
    escaped_content = content.replace('"',r'\"').replace('\n',r'\n')
    local_sudo('/bin/echo -e "%s" > %s' % (escaped_content, fullpath))

def create_dir_in_lxc(path,name):
    fullpath = '/var/lib/lxc/%s/rootfs/%s' % (name, path)
    local_sudo('mkdir -p %s' % fullpath)

def local_sudo(command):
    escaped_command = command.replace('"',r'\"')
    local('sudo sh -c "%s"' % escaped_command)


