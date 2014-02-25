# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

__all__ = [
    'ElasticLBDriver'
]


from libcloud.utils.py3 import httplib
from libcloud.utils.xml import findtext, findall
from libcloud.loadbalancer.types import State
from libcloud.loadbalancer.base import Driver, LoadBalancer, Member
from libcloud.common.aws import AWSGenericResponse, SignedAWSConnection


VERSION = '2012-06-01'
HOST = 'elasticloadbalancing.%s.amazonaws.com'
ROOT = '/%s/' % (VERSION)
NS = 'http://elasticloadbalancing.amazonaws.com/doc/%s/' % (VERSION, )


class ELBResponse(AWSGenericResponse):
    """
    Amazon ELB response class.
    """
    namespace = NS
    exceptions = {}
    xpath = 'Error'


class ELBConnection(SignedAWSConnection):
    version = VERSION
    host = HOST
    responseCls = ELBResponse


class ElasticLBDriver(Driver):
    name = 'Amazon Elastic Load Balancing'
    website = 'http://aws.amazon.com/elasticloadbalancing/'
    connectionCls = ELBConnection

    def __init__(self, access_id, secret, region):
        super(ElasticLBDriver, self).__init__(access_id, secret)
        self.region = region
        self.connection.host = HOST % (region)

    def list_protocols(self):
        return ['tcp', 'ssl', 'http', 'https']

    def list_balancers(self):
        params = {'Action': 'DescribeLoadBalancers'}
        data = self.connection.request(ROOT, params=params).object
        return self._to_balancers(data)

    def create_balancer(self, name, port, protocol, algorithm, members,
                        ex_members_availability_zones=None):
        if ex_members_availability_zones is None:
            ex_members_availability_zones = ['a']

        params = {
            'Action': 'CreateLoadBalancer',
            'LoadBalancerName': name,
            'Listeners.member.1.InstancePort': str(port),
            'Listeners.member.1.InstanceProtocol': protocol.upper(),
            'Listeners.member.1.LoadBalancerPort': str(port),
            'Listeners.member.1.Protocol': protocol.upper(),
        }

        for i, z in enumerate(ex_members_availability_zones):
            zone = ''.join((self.region, z))
            params['AvailabilityZones.member.%d' % (i + 1)] = zone

        data = self.connection.request(ROOT, params=params).object

        balancer = LoadBalancer(
            id=name,
            name=name,
            state=State.PENDING,
            ip=findtext(element=data, xpath='DNSName', namespace=NS),
            port=port,
            driver=self.connection.driver
        )
        balancer._members = []
        return balancer

    def destroy_balancer(self, balancer):
        params = {
            'Action': 'DeleteLoadBalancer',
            'LoadBalancerName': balancer.id
        }
        self.connection.request(ROOT, params=params)
        return True

    def get_balancer(self, balancer_id):
        params = {
            'Action': 'DescribeLoadBalancers',
            'LoadBalancerNames.member.1': balancer_id
        }
        data = self.connection.request(ROOT, params=params).object
        return self._to_balancers(data)[0]

    def balancer_attach_compute_node(self, balancer, node):
        params = {
            'Action': 'RegisterInstancesWithLoadBalancer',
            'LoadBalancerName': balancer.id,
            'Instances.member.1.InstanceId': node.id
        }
        self.connection.request(ROOT, params=params)
        balancer._members.append(Member(node.id, None, None, balancer=self))

    def balancer_detach_member(self, balancer, member):
        params = {
            'Action': 'DeregisterInstancesFromLoadBalancer',
            'LoadBalancerName': balancer.id,
            'Instances.member.1.InstanceId': member.id
        }
        self.connection.request(ROOT, params=params)
        balancer._members = [m for m in balancer._members if m.id != member.id]
        return True

    def balancer_list_members(self, balancer):
        return balancer._members

    def ex_list_balancer_policies(self, balancer):
        """
        Return a list of policy description string.

        :rtype: ``list`` of ``str``
        """
        params = {
            'Action': 'DescribeLoadBalancerPolicies',
            'LoadBalancerName': balancer.id
        }
        
        data = self.connection.request(ROOT, params=params).object
        return self._to_policies(data)

    def ex_list_balancer_policy_types(self):
        """
        Return a list of policy type description string.

        :rtype: ``list`` of ``str``
        """
        params = {'Action': 'DescribeLoadBalancerPolicyTypes'}
    
        data = self.connection.request(ROOT, params=params).object
        return self._to_policy_types(data)

    def ex_create_balancer_policy(self, balancer, policy_name, policy_type, policy_attributes=None):
        """
        Create a new load balancer policy

        :param LoadBalancerName: Name load balancer 
        :type  LoadBalancerName: ``str``

        :param PolicyName: Name of the load balancer policy being created
        :type  PolicyName: ``str``

        :param PolicyTypeName: Name of the base policy type being used to create this policy.
        :type  PolicyTypeName: ``str``

        :param PolicyAttributes.member.N: A list of attributes associated with the policy being created. .
        :type  PolicyAttribute.member.N: ``PolicyAttribute list``
        """
        params = {
            'Action': 'CreateLoadBalancerPolicy',
            'LoadBalancerName': balancer.id,
            'PolicyName': policy_name,
            'PolicyTypeName': policy_type
        }

        if policy_attributes is not None:
            for index, (name, value) in enumerate(policy_attributes.iteritems(), 1):
                params['PolicyAttributes.member.%d.AttributeName' % (index)] = name
                params['PolicyAttributes.member.%d.AttributeValue' % (index)] = value
        
        response = self.connection.request(ROOT, params=params)
        return response.status == httplib.OK

    def ex_delete_balancer_policy(self, balancer, policy_name):
        """
        Delete a load balancer policy

        :param LoadBalancerName: Name load balancer 
        :type  LoadBalancerName: ``str``

        :param PolicyName: Mnemonic name for the policy being deleted. 
        :type  PolicyName: ``str``
        """
        params = {
            'Action': 'DeleteLoadBalancerPolicy',
            'LoadBalancerName': balancer.id,
            'PolicyName': policy_name
        }
        
        response = self.connection.request(ROOT, params=params)
        return response.status == httplib.OK

    def ex_set_balancer_policies_listener(self, balancer, balancer_port, policies):
        """
        Associates, updates, or disables a policy with a listener on the load balancer

        :param LoadBalancerName: Name of load balancer 
        :type  LoadBalancerName: ``str``

        :param LoadBalancerPort: load balancer Port number
        :type  LoadBalancerPort: ``str``

        :param PolicyNames.member.1: List of policies to be associated with the listener.
        :type  PolicyNames.member.1: ``string list``
        """
        params = {
            'Action': 'SetLoadBalancerPoliciesOfListener',
            'LoadBalancerName': balancer.id,
            'LoadBalancerPort': str(balancer_port)
        }

        if policies:
            params = self._create_list_params(params, policies, 'PolicyNames.member.%d')
    
        response = self.connection.request(ROOT, params=params)
        return response.status == httplib.OK

    def ex_set_balancer_policies_backend_server(self, balancer, instance_port, policies):
        """
        Replaces the current set of policies associated with a port on which the back-end 
        server is listening with a new set of policies

        :param LoadBalancerName: Name of load balancer 
        :type  LoadBalancerName: ``str``

        :param InstancePort: Instance Port number
        :type  LoadBalancerPort: ``str``

        :param PolicyNames.member.1: List of policies to be associated with the balancer.
        :type  PolicyNames.member.1: ``string list`
        """
        params = {
            'Action': 'SetLoadBalancerPoliciesForBackendServer',
            'LoadBalancerName': balancer.id,
            'InstancePort': str(instance_port)
        }
        
        if policies:
            params = self._create_list_params(params, policies, 'PolicyNames.member.%d')
        
        response = self.connection.request(ROOT, params=params)
        return response.status == httplib.OK

    def ex_create_balancer_listeners(self, balancer, listeners=None):
        """
        Creates one or more listeners on a load balancer for the specified port

        :param LoadBalancerName: Name of load balancer 
        :type  LoadBalancerName: ``str``

        :param Listeners.member.N: List of LoadBalancerPort, InstancePort, Protocol, and SSLCertificateId items
        :type  Listeners.member.N: ``Listener list`
        """
        params = {
            'Action': 'CreateLoadBalancerListeners',
            'LoadBalancerName': balancer.id
        }
        
        if listeners:
            for index, listener in enumerate(listeners):
                i = index + 1
                protocol = listener[2].upper()
                params['Listeners.member.%d.LoadBalancerPort' % i] = listener[0]
                params['Listeners.member.%d.InstancePort' % i] = listener[1]
                params['Listeners.member.%d.Protocol' % i] = listener[2]
                if protocol == 'HTTPS' or protocol == 'SSL':
                    params['Listeners.member.%d.SSLCertificateId' % i] = listener[3]
        
        response = self.connection.request(ROOT, params=params)
        return response.status == httplib.OK

    def _to_policies(self, data):
        xpath = 'DescribeLoadBalancerPoliciesResult/PolicyDescriptions/member'
        return [findtext(element=el, xpath='PolicyName', namespace=NS)
                for el in findall(element=data, xpath=xpath, namespace=NS)]
    
    def _to_policy_types(self, data):
        xpath = 'DescribeLoadBalancerPolicyTypesResult/PolicyTypeDescriptions/member'
        return [findtext(element=el, xpath='PolicyTypeName', namespace=NS)
                for el in findall(element=data, xpath=xpath, namespace=NS)]
        
    def _to_balancers(self, data):
        xpath = 'DescribeLoadBalancersResult/LoadBalancerDescriptions/member'
        return [self._to_balancer(el)
                for el in findall(element=data, xpath=xpath, namespace=NS)]

    def _to_balancer(self, el):
        name = findtext(element=el, xpath='LoadBalancerName', namespace=NS)
        dns_name = findtext(el, xpath='DNSName', namespace=NS)
        port = findtext(el, xpath='LoadBalancerPort', namespace=NS)

        balancer = LoadBalancer(
            id=name,
            name=name,
            state=State.UNKNOWN,
            ip=dns_name,
            port=port,
            driver=self.connection.driver
        )

        xpath = 'Instances/member/InstanceId'
        members = findall(element=el, xpath=xpath, namespace=NS)
        balancer._members = []

        for m in members:
            balancer._members.append(Member(m.text, None, None,
                                            balancer=balancer))

        return balancer

    def _create_list_params(self, params, items, label):
        """
        return parameter list
        """
        if isinstance(items, basestring):
            items = [items]
        for index, item in enumerate(items):
            params[label % (index + 1)] = item
        return params
