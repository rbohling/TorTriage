Vagrant.configure("2") do |config|
  config.vm.box = "bento/ubuntu-24.04"
  config.vm.box_version = "202510.26.0"
  config.vm.hostname = "tortriage-shadow"
  config.vm.synced_folder ".", "/vagrant", mount_options: ["ro"], SharedFoldersEnableSymlinksCreate: false
  config.vm.network "forwarded_port", guest: 8787, host: 8787, host_ip: "127.0.0.1"
  config.vm.provider "virtualbox" do |vm|
    vm.name = "TorTriage Shadow"
    vm.memory = 6144
    vm.cpus = 4
  end
  config.vm.provision "shell", path: "demo/provision.sh"
end
