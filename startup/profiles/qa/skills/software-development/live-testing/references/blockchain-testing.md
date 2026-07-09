# Blockchain / Smart Contract Testing

Covers EVM (Ethereum, Polygon, Arbitrum, etc.), Solana, CosmWasm, and other smart contract platforms.

## Key distinction

You are testing **deployed contracts on a real chain** (local node or testnet). The contract must be compiled, deployed, and callable. You write a real client that interacts with it the way a user or dApp would.

## Setup: local blockchain node

### Hardhat / EVM local node
```bash
npx hardhat node --port 8545 &
NODE_PID=$!
for i in $(seq 1 15); do curl -sf -X POST http://localhost:8545 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' && break; sleep 1; done
```

### Anvil (Foundry)
```bash
anvil --port 8545 &
forge create src/MyContract.sol:MyContract \
  --rpc-url http://localhost:8545 \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
```

### Solana (local validator)
```bash
solana-test-validator --rpc-port 8899 &
solana cluster-version --url http://localhost:8899
```

## Deploy contracts

```bash
# EVM — via deployment script:
npx hardhat run scripts/deploy.ts --network localhost

# Or deploy raw bytecode with cast:
CAST_TX=$(cast send --rpc-url http://localhost:8545 \
  --private-key <key> \
  --create $(cat out/MyContract.sol/MyContract.bin) \
  --gas-limit 10000000)
CONTRACT_ADDR=$(echo $CAST_TX | jq -r '.contractAddress')

# Verify deployment:
cast code $CONTRACT_ADDR --rpc-url http://localhost:8545  # should return 0x...
```

## Read contract state

```bash
# Using cast (Foundry):
cast call $CONTRACT_ADDR "name()" --rpc-url http://localhost:8545
cast call $CONTRACT_ADDR "balanceOf(address)" <addr> --rpc-url http://localhost:8545
cast call $CONTRACT_ADDR "totalSupply()" --rpc-url http://localhost:8545

# JSON-RPC directly:
curl -s -X POST http://localhost:8545 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_getStorageAt","params":["'$CONTRACT_ADDR'","0x0","latest"],"id":1}'
```

## Write transactions & verify state change

```bash
cast send $CONTRACT_ADDR "mint(address,uint256)" <recipient> 100 \
  --rpc-url http://localhost:8545 \
  --private-key <key> \
  --json

# Verify:
cast call $CONTRACT_ADDR "balanceOf(address)" <recipient> --rpc-url http://localhost:8545
# Should now return 100
```

## Test with a real frontend (dApp)

If the project includes a web frontend:
```bash
npm run build && npm run preview -- --port 3000 &

# Use browser tools:
browser_navigate("http://localhost:3000")
# Connect MetaMask-equivalent to localhost:8545
# Test: connect wallet, call contract function via UI, verify on-chain state
```

## Blockchain-specific edge cases

Cases beyond the universal categories in SKILL.md:

| Category | Tests |
|----------|-------|
| Reentrancy | Call a function that calls back into the contract before state updates |
| Integer overflow/underflow | `type(uint256).max + 1`, `0 - 1` (pre-0.8 Solidity) |
| Access control | Call admin-only functions from a non-admin account |
| Zero address | Send to `address(0)`, approve `address(0)` |
| Approval race | Front-run an approval by transferring first |
| Gas limits | Call a function that loops over a large array — does it run out of gas? |
| Pause/unpause | If the contract is pausable, test interactions while paused |
| Upgrade proxy | If using a proxy pattern, upgrade and verify state is preserved |
| Event emission | Verify events are emitted with correct indexed/non-indexed params |
| ETH send to contract | Send ETH to a contract without a receive() function |
| Flash loan | Take a flash loan and manipulate price or state within one tx |
| Frontrunning | Submit two conflicting txs, see which confirms |
| Self-destruct | If applicable, call selfdestruct and verify |
| Large token amounts | `mint(type(uint256).max)` — overflow or correct? |
| Empty calldata | Send a tx with empty data to the contract |

## Solana-specific

```bash
solana program deploy target/deploy/my_program.so --url http://localhost:8899
solana transfer <recipient> 1.0 --url http://localhost:8899
solana confirm <tx_signature> --url http://localhost:8899 -v
```

## Evidence

- Transaction hashes
- Pre/post state diffs (`cast call` before and after)
- Block explorer links (if testnet)
- Event logs from the transaction receipt:
  ```bash
  cast receipt <tx_hash> --rpc-url http://localhost:8545 --json
  ```
- Revert reasons (if a tx fails):
  ```bash
  cast run <tx_hash> --rpc-url http://localhost:8545
  ```
- Gas used for each operation
