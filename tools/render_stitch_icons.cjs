// Pré-processamento opcional; o app distribuído usa os PNGs já presentes.
// Passe o caminho do pacote sharp como primeiro argumento se ele não for local.
const fs = require('node:fs');
const path = require('node:path');
const sharp = require(process.argv[2] || 'sharp');
const directory = path.resolve(__dirname, '../assets/stitch/icons');

async function main() {
  const files = fs.readdirSync(directory).filter(name => name.endsWith('.svg'));
  await Promise.all(files.map(async name => {
    const input = fs.readFileSync(path.join(directory, name));
    await sharp(input, {density: 576})
      .resize(192, 192).png()
      .toFile(path.join(directory, name.replace(/\.svg$/, '.png')));
  }));
  process.stdout.write(`${files.length} ícones renderizados a 192 px com transparência.\n`);
}
main().catch(error => { process.stderr.write(error.message + '\n'); process.exitCode = 1; });
