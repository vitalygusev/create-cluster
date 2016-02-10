create-cluster
==============
A set of scripts for creating Fuel cluster

Introduction
------------
The main goal of these scripts is the automatic creation of Fuel cluster. 
All parameters are taken from the configuration file `settings.txt`.

How to use
----------
Firstly, you should install `python-keystonclient`:
```bash
$ sudo apt-get install python-keystonclient
```
Then change the settings in the configuration file on your own and just run the following command
```bash
$ python create_cluster.py settings.txt
```
