import json
from web3 import Web3
from utils.constants import *

# Data Struct to store Pool information
class PoolData:
    def __init__(self, address: str):
        self.address = address
        self.voting_power = 0

    def to_dict(self):
        return {'address': self.address, 'voting_power': self.voting_power}

    def __repr__(self):
        return json.dumps(self.to_dict(), indent=4)

# Data Struct to store Chain information
class ChainData:
    def __init__(self, name: str, rpc_url: str):
        self.pools = []
        self.name = name
        self.rpc_url = rpc_url
        self.total_voting_weight = 0
        self.existing_buffer_cap = 0
        self.existing_rate_limit = 0
        self.expected_emissions = 0

    def __repr__(self):
        return f"Name: {self.name}\nTotal Voting Weight: {self.total_voting_weight}\nExpected Emissions: {self.expected_emissions}\nExisting Buffer Cap: {self.existing_buffer_cap}\nExisting Rate Limit: {self.existing_rate_limit}\nPools={self.pools}\n"

# Data Struct to store new limits for each Chain
class NewLimitData:
    def __init__(self, name: str, new_buffer_cap: int, new_rate_limit: int):
        self.name = name
        self.new_buffer_cap = new_buffer_cap
        self.new_rate_limit = new_rate_limit

    def __repr__(self):
        return f"Name: {self.name}\nNew Buffer Cap: {self.new_buffer_cap:.0f}\nNew Rate Limit: {self.new_rate_limit:.0f}"

chains: dict[int, ChainData] = {
    34443: ChainData("Mode", MODE_RPC_URL),
    1135: ChainData("Lisk", LISK_RPC_URL),
    252: ChainData("Fraxtal", FRAXTAL_RPC_URL),
}

web3 = Web3(Web3.HTTPProvider(OPTIMISM_RPC_URL))
root_pool_factory = web3.eth.contract(address=ROOT_POOL_FACTORY_ADDRESS, abi=root_pool_factory_abi)
cl_root_pool_factory = web3.eth.contract(address=CL_ROOT_POOL_FACTORY_ADDRESS, abi=cl_root_pool_factory_abi)
voter = web3.eth.contract(address=VOTER_ADDRESS, abi=voter_abi)
voting_escrow = web3.eth.contract(address=VOTING_ESCROW, abi=voting_escrow_abi)
minter = web3.eth.contract(address=MINTER, abi=minter_abi)

root_pools = []

def print_chain_info():
    print("-" * 40)
    for chain_id, chain_data in chains.items():
        print(f"Chain ID: {chain_id}")
        print(chain_data)
        print("-" * 40)  # Divider for clarity

def fetch_pools():
    # fetch v2 superchain pools
    root_pools = root_pool_factory.functions.allPools().call();

    # fetch cl superchain pools
    cl_root_pools = cl_root_pool_factory.functions.allPools().call();

    # concatenate pool lists
    root_pools.extend(cl_root_pools)

    # organize by chainid
    for pool in root_pools:
        root_pool = web3.eth.contract(address=pool, abi=root_pool_abi)
        chainid = root_pool.functions.chainid().call()
        chains[chainid].pools.append(PoolData(pool))

def fetch_voting_weights():
    superchain_votes = 0
    for chain_id, chain_data in chains.items():
        for pool in chain_data.pools:
            pool.voting_power = voter.functions.weights(pool.address).call()
            chain_data.total_voting_weight += pool.voting_power
        superchain_votes += chain_data.total_voting_weight

    return superchain_votes

def fetch_existing_buffers():
    for chain_id, chain_data in chains.items():
        web3_temp = Web3(Web3.HTTPProvider(chain_data.rpc_url))
        xerc20 = web3_temp.eth.contract(address=XERC20, abi=xerc20_abi)
        chain_data.existing_buffer_cap = xerc20.functions.bufferCap(MESSAGE_MODULE).call()
        chain_data.existing_rate_limit = xerc20.functions.rateLimitPerSecond(MESSAGE_MODULE).call()

# Main function
def main():
    # Fetch pools and organize by chain
    fetch_pools()

    # get each pool votes and sum it up
    total_voting_superchain = fetch_voting_weights()

    fetch_existing_buffers()

    # total voting power at current timestamp
    total_voting_weight = voting_escrow.functions.totalSupply().call()
    # estimated weekly emissions for next epoch
    weekly = minter.functions.weekly().call()

    # Compare voting weights with total supply
    print(f"Total Voting Power: {total_voting_weight}")
    print(f"Total Superchain Votes: {total_voting_superchain}")

    new_chain_limits: dict[int, NewLimitData] = {}

    print("-" * 40)
    for chain_id, chain_data in chains.items():
        # calculate expected emissions based on chain emissions
        weights_percentage = chain_data.total_voting_weight/total_voting_weight
        chain_data.expected_emissions = weekly * weights_percentage * 1.2 # add 1.2x buffer on top of expected emissions
        print(f"Chain ID: {chain_id}")
        print(f"Name: {chain_data.name}")
        print(f"Number of Pools:: {len(chain_data.pools)}")
        print(f"Pools: {chain_data.pools}")
        print(f"Chain Voting Weight: {chain_data.total_voting_weight:.0f}")
        print(f"Percentage of Total Votes: {weights_percentage*100:.3f}%")
        print(f"Expected Emissions: {chain_data.expected_emissions:.0f}")
        print(f"Existing Buffer Cap: {chain_data.existing_buffer_cap:.0f}")
        print(f"Expected Rate Limit: {chain_data.expected_emissions / 604800:.0f}")
        print(f"Existing Rate Limit: {chain_data.existing_rate_limit:.0f}")
        if chain_data.expected_emissions > chain_data.existing_buffer_cap:
            print("*" * 40)
            print(f"WARNING: Buffer cap should be updated at least to: {chain_data.expected_emissions:.0f}")
            print(f"WARNING: Rate limit should be updated at least to: {chain_data.expected_emissions / 604800:.0f}")
            new_chain_limits[chain_id] = NewLimitData(chain_data.name, chain_data.expected_emissions, chain_data.expected_emissions / 604800)
        print("-" * 40 + "\n")  # Divider for readability

    return new_chain_limits

if __name__ == "__main__":
    new_chain_limits = main()

    if not new_chain_limits:
        print("No new limits required.")
        print("-" * 40)
        for chain_id, chain_data in chains.items():
            print(f"Chain ID: {chain_id}")
            print(f"Name: {chain_data.name}")
            print(f"Chain Voting Weight: {chain_data.total_voting_weight / 1e18:.0f}")
            print(f"Expected Emissions: {chain_data.expected_emissions / 1e18:.0f}")
            print(f"Existing Buffer Cap: {chain_data.existing_buffer_cap / 1e18:.0f}")
            print("-" * 40 + "\n")
    else:
        print("WARNING: New Chain Limits required")
        print("-" * 40)
        for chain_id, chain_limits in new_chain_limits.items():
            print(f"Chain ID: {chain_id}")
            print(chain_limits)
            print("-" * 40)
