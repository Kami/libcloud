from libcloud.compute.types import Provider
from libcloud.compute.providers import get_driver

ACCESS_ID = 'your access id'
SECRET_KEY = 'your secret key'

cls = get_driver(Provider.ELB)
driver = cls(key=ACCESS_ID, secret=SECRET_KEY, region='')

print driver.list_balancers()

driver.ex_delete_balancer_policy(
    name='MyLB',
    policy_name='EnableProxyProtocol',
    )
