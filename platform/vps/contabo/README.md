# Contabo client container: pm2 the Hostinger way

A Contabo client runs in its own container, with `/home/node/.openclaw` on a persistent
volume and `HOME=/home/node` on the throwaway container layer. The Command Center runs
under pm2 as `blackceo-command-center` (`bash scripts/cc-start.sh --port 4000`, from the
Command Center's `ecosystem.config.cjs`), exactly as on Hostinger. For every shell to
reach that one pm2 daemon, including a bare `docker exec` from the fleet roll, set up
three things.

1. **Compose `environment:`** for the openclaw service (this must be in compose, not only
   in `.env`):

   ```yaml
       environment:
         PATH: /home/node/.openclaw/npm-global/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
         PM2_HOME: /home/node/.openclaw/.pm2
         NPM_CONFIG_PREFIX: /home/node/.openclaw/npm-global
         MASTER_FILES_DIR: /home/node/.openclaw/openclaw-master-files
   ```

   `MASTER_FILES_DIR` keeps company folders and playbooks on the volume. `$HOME/Downloads`
   is the container's temporary layer: a recreate deletes it (one client lost a whole
   company folder that way).

   Keep `/home/node/.openclaw/bin` OFF this PATH: it can hold a non-executable uv `env`
   file that shadows `/usr/bin/env`.

2. **Compose `command: [bash, /home/node/.openclaw/scripts/container-startup.sh]`**, with
   [`container-startup.sh`](container-startup.sh) copied to
   `<volume>/scripts/container-startup.sh`. It links `$HOME/.pm2` to `PM2_HOME` (moving a
   stray folder aside), resurrects the saved pm2 list, then exec's the gateway.

3. **`pm2 save` after the Command Center is started**, so `dump.pm2` in `PM2_HOME` lists
   `blackceo-command-center`. The Skill 32 installer does this. On an existing box, check
   with `pm2 ls` from a bare `docker exec -u node <container>` shell. Exactly one pm2
   daemon should be running.

A root `docker exec` shell has `HOME=/root`. Without the compose `PM2_HOME`, it starts a
daemon of its own.

The fleet roll checks all three before it touches the Command Center. If any is missing,
it fails the box with "Command Center not under pm2", "pm2 is not on this shell's PATH"
or "... PM2_HOME ...", and changes nothing.
