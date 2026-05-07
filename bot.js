const mineflayer = require('mineflayer');
const { pathfinder, Movements, goals } = require('mineflayer-pathfinder');
const express = require('express');
const bodyParser = require('body-parser');
const fs = require('fs');

// Load config
const config = JSON.parse(fs.readFileSync('config.json', 'utf8'));

// Create Bot
console.log(`Attempting to connect to ${config.minecraft_host}:${config.minecraft_port} as ${config.bot_username}...`);
const bot = mineflayer.createBot({
  host: config.minecraft_host,
  port: config.minecraft_port,
  username: config.bot_username,
  version: config.minecraft_version
});

// Load Pathfinder
bot.loadPlugin(pathfinder);

bot.on('login', () => {
  console.log('--- LOGIN SUCCESSFUL ---');
  console.log(`Logged in as ${bot.username} to ${config.minecraft_host}:${config.minecraft_port}`);
});

bot.on('error', (err) => {
  console.log('--- CONNECTION ERROR ---');
  console.error(err);
});

bot.on('kicked', (reason) => {
  console.log('--- KICKED FROM SERVER ---');
  console.log(reason);
});

bot.on('end', (reason) => {
  console.log(`--- DISCONNECTED: ${reason} ---`);
});

let movements;

bot.once('spawn', () => {
  console.log(`--- BOT SPAWNED at ${bot.entity.position} ---`);
  const mcData = require('minecraft-data')(bot.version);
  movements = new Movements(bot, mcData);
  bot.pathfinder.setMovements(movements);
});

// Express API for Python Connector
const app = express();
app.use(bodyParser.json());

app.post('/action', async (req, res) => {
  const { type, x, y, z, range = 1 } = req.body;
  console.log(`Received action: ${type} at (${x}, ${y}, ${z})`);

  try {
    if (type === 'pathfind') {
      let goal;
      if (y !== undefined && y !== null) {
        goal = new goals.GoalNear(x, y, z, range);
      } else {
        goal = new goals.GoalNearXZ(x, z, range);
      }

      await bot.pathfinder.goto(goal);
      res.json({ status: 'success', message: 'Reached destination' });
    } else if (type === 'status') {
      res.json({ status: 'success', pos: bot.entity.position });
    } else {
      res.status(400).json({ status: 'error', message: 'Unknown action type' });
    }
  } catch (err) {
    console.error(err);
    res.status(500).json({ status: 'error', message: err.message });
  }
});

app.listen(config.api_port, () => {
  console.log(`JS Connector listening on port ${config.api_port}`);
});

bot.on('error', console.error);
bot.on('kicked', console.log);
