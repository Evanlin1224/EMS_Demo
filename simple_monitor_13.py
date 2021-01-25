# Copyright (C) 2016 Nippon Telegraph and Telephone Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from operator import attrgetter

from ryu.app import simple_switch_13
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.lib import hub
import paramiko
import logging
import time

###
now=0
past=0
past1=0
i=0
num=0

ovs_ip = "192.168.1.1"
ovs_uid = "root"
ovs_pwd = "letmein"
class SimpleMonitor13(simple_switch_13.SimpleSwitch13):
    
    
    
    

    def __init__(self, *args, **kwargs):
        super(SimpleMonitor13, self).__init__(*args, **kwargs)
        self.datapaths = {}
        self.monitor_thread = hub.spawn(self._monitor)

    @set_ev_cls(ofp_event.EventOFPStateChange,
                [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if datapath.id not in self.datapaths:
                self.logger.debug('register datapath: %016x', datapath.id)
                self.datapaths[datapath.id] = datapath
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                self.logger.debug('unregister datapath: %016x', datapath.id)
                del self.datapaths[datapath.id]

    def _monitor(self):
        while True:
            for dp in self.datapaths.values():
                self._request_stats(dp)
            hub.sleep(5)

    def _request_stats(self, datapath):
        self.logger.debug('send stats request: %016x', datapath.id)
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        req = parser.OFPFlowStatsRequest(datapath)
        datapath.send_msg(req)

        req = parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats_reply_handler(self, ev):
        global now
        global past
        global i
        global past1
        global num
        global ovs_ip
        global ovs_uid
        global ovs_pwd

        body = ev.msg.body

        self.logger.info('datapath         '
                         'in-port  eth-dst           '
                         'out-port packets  bytes')
        self.logger.info('---------------- '
                         '-------- ----------------- '
                         '-------- -------- --------')
        for stat in sorted([flow for flow in body if flow.priority == 1],
                           key=lambda flow: (flow.match['in_port'],
                                             flow.match['eth_dst'])):
            self.logger.info('%016x %8x %17s %8x %8d %8d',
                             ev.msg.datapath.id,
                             stat.match['in_port'], stat.match['eth_dst'],
                             stat.instructions[0].actions[0].port,
                             stat.packet_count, stat.byte_count)
            if stat.match['in_port']==62: #針對62這個port所接受的封包數量
                if i == 0: #封包第一次進來
                    now = stat.byte_count
                    #past = stat.byte_count
                    past1 = 0
                else:
                    now = stat.byte_count
                print("Now packet bytes num:"+str(now - past1))
            num = now - past1 #計算封包數量
            past1 = now
        i = i + 1
        
        if num >= 200000: #封包數量超過200000bytes
            ssh = paramiko.SSHClient() 
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(ovs_ip,username=ovs_uid,password=ovs_pwd)
            print("ssh connect!")
            my_command1 = "ovs-ofctl add-meter ovs-br meter=1,kbps,band=type=drop,rate=30 -O openflow13"
            stdin, stdout, stderr = ssh.exec_command(my_command1)
            channel = stdout.channel
            channel.recv_exit_status()
            time.sleep(1)
            my_command2 = "ovs-ofctl add-flow ovs-br in_port=eth1.4,action=meter:1,output=eth1.3 -O openflow13"
            stdin, stdout, stderr = ssh.exec_command(my_command2)
            channel = stdout.channel
            channel.recv_exit_status()
            ssh.close()
            

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        global now
        global past
        global i
        body = ev.msg.body

        self.logger.info('datapath         port     '
                         'rx-pkts  rx-bytes rx-error '
                         'tx-pkts  tx-bytes tx-error')
        self.logger.info('---------------- -------- '
                         '-------- -------- -------- '
                         '-------- -------- --------')
        for stat in sorted(body, key=attrgetter('port_no')):
            self.logger.info('%016x %8x %8d %8d %8d %8d %8d %8d',
                             ev.msg.datapath.id, stat.port_no,
                             stat.rx_packets, stat.rx_bytes, stat.rx_errors,
                             stat.tx_packets, stat.tx_bytes, stat.tx_errors)

