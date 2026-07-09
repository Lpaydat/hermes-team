# Daemon / Broker / Service Testing

Covers message brokers (RabbitMQ, NATS, Kafka), daemons (systemd services, background workers), schedulers, and long-running services that maintain state.

## Start

1. Build (see SKILL.md).
2. Start with the real configuration:
   ```bash
   ./<daemon> --config config/daemon.toml &
   DAEMON_PID=$!
   # Or via Docker:
   docker compose up -d
   ```
3. Wait for readiness — daemons often need initialization time:
   ```bash
   for i in $(seq 1 30); do
     <daemon> status && break
     ss -tlnp | grep -q :<port> && break
     sleep 1
   done
   ```

## Confirm it's alive

```bash
ps aux | grep <daemon>
kill -0 $DAEMON_PID && echo "running" || echo "dead"
ss -tlnp | grep <port>
lsof -i :<port>
curl http://localhost:<port>/health
<daemon> status
<daemon> ping
```

## Message broker testing

### RabbitMQ
```bash
rabbitmqadmin publish exchange=amq.default routing_key=test.queue \
  payload='{"event": "test"}' \
  properties='{"content_type": "application/json"}'

rabbitmqadmin get queue=test.queue ack=true
rabbitmqadmin list queues name messages
rabbitmqadmin list bindings
```

### NATS
```bash
nats sub test.subject &
SUB_PID=$!
nats pub test.subject '{"event": "test"}'
wait $SUB_PID  # check output contains the message
nats request test.subject "ping"
```

### Kafka
```bash
kafka-topics --create --bootstrap-server localhost:9092 \
  --topic test-topic --partitions 3 --replication-factor 1

echo '{"event": "test"}' | kafka-console-producer \
  --bootstrap-server localhost:9092 --topic test-topic

kafka-console-consumer --bootstrap-server localhost:9092 \
  --topic test-topic --from-beginning --max-messages 1

kafka-consumer-groups --bootstrap-server localhost:9092 --describe --group <group>
```

## Daemon-specific edge cases

Cases beyond the universal categories in SKILL.md:

| Category | Tests |
|----------|-------|
| Graceful shutdown | SIGTERM — does it finish in-flight work before exiting? |
| Forced shutdown | SIGKILL — does it leave corrupt state on restart? |
| Restart recovery | Kill, restart — does it recover persisted state? |
| Connection flood | Open 1000 simultaneous connections — does it handle or crash? |
| Message ordering | Send messages rapidly — are they delivered in order? |
| Message loss | Kill the daemon mid-delivery — are messages lost or redelivered? |
| Delivery guarantees | Verify at-least-once / exactly-once matches the spec |
| Backpressure | Produce faster than the consumer processes — does it queue, drop, or crash? |
| Config reload | SIGHUP or reload command — does config hot-reload? |
| Dependency failure | What does the daemon report when a dependency (DB, upstream) is down? |
| Resource leaks | Run for 10 minutes with active load — does memory/CPU grow unbounded? |
| Deadline/timeout | Client connects but never sends data — does the daemon timeout the connection? |
| Protocol violations | Send malformed binary data, partial frames, oversized messages |

## Scheduler/cron-like daemons

```bash
<daemon> list-jobs                          # verify schedule
<daemon> run-job <job-name>                 # trigger manually if supported

# Verify scheduled execution:
<daemon> logs --tail 50 | grep "job executed"

# Make a job fail, verify retry/failure handling
```

## Teardown

```bash
kill -TERM $DAEMON_PID
sleep 2
kill -0 $DAEMON_PID 2>/dev/null && kill -KILL $DAEMON_PID
rm -rf /tmp/<daemon>-state/
docker compose down -v
```

## Evidence

- Process status before and after tests (`ps`, `kill -0`)
- Port listing (`ss -tlnp`)
- Message delivery logs (actual consumed message content)
- Queue depth / consumer lag before and after
- Daemon logs showing handling of test scenarios
- Memory/CPU over time (for leak detection):
  ```bash
  ps -o pid,rss,%cpu,%mem,cmd -p $DAEMON_PID
  ```
