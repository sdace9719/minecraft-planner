const mcDataFactory = require('minecraft-data');
const fs = require('fs');

const version = process.argv[2] || '1.20.1';
const action = process.argv[3];
const itemName = process.argv[4];

let mcData;
try {
  mcData = mcDataFactory(version);
} catch (e) {
  console.error(JSON.stringify({ error: `Version ${version} not supported` }));
  process.exit(1);
}

const TOOL_TIERS = ['wooden', 'stone', 'iron', 'diamond', 'netherite', 'golden'];
if (action === 'get_item') {
  const item = mcData.itemsByName[itemName] || mcData.blocksByName[itemName];
  if (!item) {
    console.log(JSON.stringify({ error: `Item ${itemName} not found` }));
  } else {
    const response = { ...item };
    if (mcData.blocksByName[itemName]) {
      response.hardness = mcData.blocksByName[itemName].hardness;
      response.blockLoot = mcData.blockLoot[itemName];
    }
    console.log(JSON.stringify(response));
  }
} else if (action === 'get_recipes') {
  const item = mcData.itemsByName[itemName] || mcData.blocksByName[itemName];
  if (!item) {
    console.log(JSON.stringify({ error: `Item ${itemName} not found` }));
  } else {
    const recipes = mcData.recipes[item.id] || [];
    const response = {
      item: { ...item },
      recipes: recipes,
      idMap: {}
    };
    if (mcData.blocksByName[itemName]) {
      response.item.hardness = mcData.blocksByName[itemName].hardness;
      response.item.blockLoot = mcData.blockLoot[itemName];
    }
    // Also check if this item is a drop from any block
    response.droppedFrom = [];
    Object.values(mcData.blockLoot).forEach(loot => {
      const drops = loot.drops.filter(d => d.item === itemName);
      drops.forEach(drop => {
        response.droppedFrom.push({
          block: loot.block,
          silkTouch: drop.silkTouch || false,
          noSilkTouch: drop.noSilkTouch || false
        });
      });
    });

    recipes.forEach(recipe => {
      const ids = [];
      if (recipe.ingredients) ids.push(...recipe.ingredients);
      if (recipe.inShape) recipe.inShape.flat().forEach(id => { if (id !== null) ids.push(id); });
      ids.forEach(id => {
        if (!response.idMap[id]) {
          const ing = mcData.items[id] || mcData.blocks[id];
          if (ing) response.idMap[id] = ing.name;
        }
      });
    });
    console.log(JSON.stringify(response));
  }
} else if (action === 'get_sources') {
  const item = mcData.itemsByName[itemName] || mcData.blocksByName[itemName];
  if (!item) {
    console.log(JSON.stringify({ error: `Item ${itemName} not found` }));
  } else {
    const response = {
      item: { ...item },
      droppedFrom: []
    };
    Object.values(mcData.blockLoot).forEach(loot => {
      const drops = loot.drops.filter(d => d.item === itemName);
      drops.forEach(drop => {
        response.droppedFrom.push({
          block: loot.block,
          silkTouch: drop.silkTouch || false,
          noSilkTouch: drop.noSilkTouch || false
        });
      });
    });
    console.log(JSON.stringify(response));
  }
} else if (action === 'get_tool_info') {
  const block = mcData.blocksByName[itemName];
  if (!block) {
    console.log(JSON.stringify({ error: `Block ${itemName} not found` }));
  } else {
    let harvestTools = block.harvestTools;
    let dropName = block.name;
    if (block.drops && block.drops.length > 0) {
      const dropItem = mcData.items[block.drops[0]];
      if (dropItem) dropName = dropItem.name;
    }
    const combinedTools = { ...(harvestTools || {}) };
    const response = {
      needsTool: Object.keys(combinedTools).length > 0,
      hardness: block.hardness,
      dropName: dropName,
      availableTools: Object.keys(combinedTools).map(id => {
        const item = mcData.items[id];
        if (!item) return null;
        let tier = TOOL_TIERS.findIndex(t => item.name.includes(t));
        if (tier === -1) tier = 999;
        return { name: item.name, tier: tier, durability: item.maxDurability || item.maxDamage };
      }).filter(t => t !== null)
    };
    console.log(JSON.stringify(response));
  }
} else {
  console.error(JSON.stringify({ error: "Invalid action" }));
  process.exit(1);
}
