const mcDataFactory = require('minecraft-data');
const fs = require('fs');

const config = JSON.parse(fs.readFileSync('config.json', 'utf8'));
const version = config.minecraft_version || '1.21.1';

let mcData;
try {
  mcData = mcDataFactory(version);
} catch (e) {
  console.error(JSON.stringify({ error: `Version ${version} not supported` }));
  process.exit(1);
}

const allMaterials = {};

const items = Object.values(mcData.items);
const blocks = Object.values(mcData.blocks);

items.forEach(item => {
  allMaterials[item.name] = {
    name: item.name,
    displayName: item.displayName,
    stackSize: item.stackSize,
    isBlock: false
  };
});

blocks.forEach(block => {
  if (!allMaterials[block.name]) {
    allMaterials[block.name] = {
      name: block.name,
      displayName: block.displayName,
      stackSize: block.stackSize || 64,
      isBlock: true
    };
  } else {
    allMaterials[block.name].isBlock = true;
  }
});

fs.writeFileSync('extracted_materials.json', JSON.stringify(Object.values(allMaterials), null, 2));
console.log(`Extracted ${Object.keys(allMaterials).length} materials to extracted_materials.json`);
