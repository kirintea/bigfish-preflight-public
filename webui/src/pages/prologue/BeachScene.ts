import Phaser from "phaser";
import type { BeachState } from "./types";

export const shore = (col: number) => 18 + Math.floor(3 * Math.sin(col / 9));
const north = (col: number) => 3 + Math.floor(1.5 * Math.cos(col / 6));
const trees = [
  [96, 64],
  [208, 32],
  [352, 64],
  [864, 32],
  [1024, 64],
  [1184, 32],
  [1312, 96],
];
export const solids = [
  [32, 224, 128, 160],
  [96, 96, 416, 64],
  [768, 64, 576, 96],
  [1280, 256, 96, 160],
  ...trees.map(([x, y]) => [x + 20, y + 56, 22, 40]),
];
const color = {
  water: 0x37abc1,
  deep: 0x318fac,
  foam: 0xd7f3db,
  sand: 0xf1dea0,
  sandLight: 0xfae9b5,
  grass: 0x659f5b,
  grassDark: 0x438b59,
};

export class BeachScene extends Phaser.Scene {
  state: BeachState | null = null;
  keys = { dx: 0, dy: 0 };
  interact: () => void = () => {};
  targetPoint: (x: number, y: number) => void = () => {};
  debug = false;
  onReady: () => void = () => {};
  private actors = new Map<string, Phaser.GameObjects.Sprite>();
  private names = new Map<string, Phaser.GameObjects.Text>();
  private props = new Map<string, Phaser.GameObjects.Container>();
  private waves!: Phaser.GameObjects.Graphics;
  private overlay!: Phaser.GameObjects.Graphics;
  private activeKeys = new Set<string>();
  private tickAt = 0;
  constructor() {
    super("beach");
  }
  create() {
    const terrain = this.add.graphics();
    terrain.fillStyle(color.water).fillRect(0, 0, 1408, 800);
    for (let col = 0; col < 44; col++) {
      const edge = (shore(col) + 1) * 32;
      terrain.fillStyle(color.sand).fillRect(col * 32, 0, 32, edge);
      terrain.fillStyle(color.sandLight).fillRect(col * 32, edge - 54, 32, 44);
      terrain.fillStyle(0xd5c78a).fillRect(col * 32, edge - 4, 32, 8);
      terrain.fillStyle(color.foam).fillRect(col * 32, edge + 4, 32, 6);
      terrain.fillStyle(0x78c7c9).fillRect(col * 32, edge + 10, 32, 15);
      const grassEnd = north(col) * 32;
      terrain.fillStyle(color.grass).fillRect(col * 32, 0, 32, grassEnd);
      terrain
        .fillStyle(color.grassDark)
        .fillRect(col * 32, grassEnd - 5, 32, 5);
      terrain.fillStyle(0x8db666).fillRect(col * 32, grassEnd - 12, 32, 7);
    }
    // Seeded small marks add detail while keeping the beach readable.
    let seed = 71;
    const random = () => {
      seed = (seed * 16807) % 2147483647;
      return seed / 2147483647;
    };
    for (let i = 0; i < 900; i++) {
      const x = Math.floor((random() * 1408) / 4) * 4,
        y = Math.floor((random() * 800) / 4) * 4,
        col = Math.floor(x / 32),
        row = Math.floor(y / 32);
      if (row <= shore(col) && row >= north(col)) {
        terrain
          .fillStyle(random() > 0.5 ? 0xd3bf85 : 0xf8e9b8, 0.8)
          .fillRect(x, y, random() > 0.7 ? 8 : 4, 2);
      } else if (row < north(col)) {
        terrain
          .fillStyle(random() > 0.5 ? 0x78b467 : 0x539855)
          .fillRect(x, y, 5, 3);
      }
    }
    // Tide pools and rock formations are independent terrain shapes.
    for (const [x, y, w, h] of solids.slice(0, 4))
      this.rock(terrain, x, y, w, h);
    for (const [x, y] of trees) this.palm(x, y);
    for (const [x, y] of [
      [520, 105],
      [710, 90],
      [1220, 170],
      [55, 180],
      [980, 145],
      [200, 190],
    ]) {
      terrain
        .fillStyle(0x75a654)
        .fillRect(x, y, 20, 5)
        .fillRect(x + 5, y - 8, 5, 16);
      terrain.fillStyle(0x376c49).fillRect(x + 12, y - 5, 4, 10);
    }
    this.waves = this.add.graphics().setDepth(1);
    this.makeActors();
    this.overlay = this.add.graphics().setDepth(1000);
    this.input.keyboard?.on("keydown", (e: KeyboardEvent) => {
      if (
        (e.target as HTMLElement)?.closest(
          "input,textarea,select,[contenteditable]",
        )
      )
        return;
      const key = e.key.toLowerCase();
      if (
        [
          "arrowup",
          "arrowdown",
          "arrowleft",
          "arrowright",
          " ",
          "w",
          "a",
          "s",
          "d",
          "e",
        ].includes(key)
      ) {
        e.preventDefault();
        this.activeKeys.add(key);
      }
      if ((key === "e" || key === " ") && !e.repeat) this.interact();
    });
    this.input.keyboard?.on("keyup", (e: KeyboardEvent) =>
      this.activeKeys.delete(e.key.toLowerCase()),
    );
    this.game.events.on("blur", () => this.activeKeys.clear());
    this.input.on("pointerdown", (p: Phaser.Input.Pointer) =>
      this.targetPoint(p.worldX, p.worldY),
    );
    this.tickAt = this.time.now;
    this.onReady();
  }
  private rock(
    g: Phaser.GameObjects.Graphics,
    x: number,
    y: number,
    w: number,
    h: number,
  ) {
    g.fillStyle(0xb5ae82).fillRect(x + 5, y + h - 12, w, h / 4);
    for (let i = 0; i < w; i += 32) {
      const top = y + (i % 64 ? 12 : 0);
      g.fillStyle(0x748d8c).fillRect(x + i, top, 32, h - 6);
      g.fillStyle(0x9eb2a6).fillRect(x + i, top, 32, 14);
      g.fillStyle(0x536f73).fillRect(x + i + 25, top + 14, 7, h - 20);
      g.fillStyle(0xb7c5ae).fillRect(x + i + 4, top + 3, 17, 5);
    }
    g.fillStyle(0x4d8b53).fillRect(x, y - 7, w, 9);
  }
  private palm(x: number, y: number) {
    const g = this.add.graphics().setDepth(y + 98);
    g.fillStyle(0x96814b, 0.22).fillEllipse(x + 38, y + 94, 80, 22);
    g.fillStyle(0x8c6f40).fillRect(x + 28, y + 36, 16, 61);
    g.fillStyle(0xc3a063).fillRect(x + 28, y + 36, 6, 59);
    for (let n = 0; n < 5; n++)
      g.fillStyle(0x785d39).fillRect(x + 28, y + 44 + n * 10, 16, 3);
    for (const [px, py, w, h] of [
      [-7, 30, 43, 12],
      [9, 14, 30, 17],
      [27, 4, 13, 38],
      [39, 18, 35, 13],
      [42, 33, 48, 10],
      [-15, 44, 47, 10],
      [40, 44, 45, 12],
    ]) {
      g.fillStyle(0x28764f).fillRect(x + px, y + py, w, h);
      g.fillStyle(0x4d9b55).fillRect(x + px, y + py, w, h / 2);
    }
    g.fillStyle(0x6b5639)
      .fillRect(x + 28, y + 36, 8, 8)
      .fillRect(x + 40, y + 38, 7, 7);
  }
  private makeActors() {
    const palettes: Record<
      string,
      { hair: string; shirt: string; trim: string }
    > = {
      player: { hair: "#273f52", shirt: "#f6f1d5", trim: "#366777" },
      "npc-bigfish": { hair: "#6896ac", shirt: "#e9c07d", trim: "#c78c56" },
      "npc-claude": { hair: "#d3a4a8", shirt: "#667056", trim: "#ad736f" },
      cook: { hair: "#b78354", shirt: "#f9f4de", trim: "#ba674e" },
      merchant: { hair: "#655b76", shirt: "#d89e73", trim: "#55567d" },
      farmer: { hair: "#b6a066", shirt: "#73965e", trim: "#506842" },
      adventurer: { hair: "#8a5f4e", shirt: "#ae655e", trim: "#f2ce8e" },
      mechanic: { hair: "#6c7b75", shirt: "#8196a3", trim: "#455d6f" },
    };
    for (const [template, p] of Object.entries(palettes))
      for (const facing of ["down", "left", "right", "up"])
        for (let frame = 0; frame < 3; frame++) {
          const key = `${template}-${facing}-${frame}`;
          if (this.textures.exists(key)) continue;
          const tex = this.textures.createCanvas(key, 32, 44)!;
          const c = tex.context;
          c.imageSmoothingEnabled = false;
          const r = (
            color: string,
            x: number,
            y: number,
            w: number,
            h: number,
          ) => {
            c.fillStyle = color;
            c.fillRect(x, y, w, h);
          };
          const offset = frame === 1 ? -1 : frame === 2 ? 1 : 0;
          c.fillStyle = "#33545d38";
          c.fillRect(5, 39, 22, 4);
          r("#3d5559", 9, 31, 6, 9 + offset);
          r("#3d5559", 18, 31, 6, 9 - offset);
          r("#354451", 7, 39 + offset, 8, 3);
          r("#354451", 18, 39 - offset, 8, 3);
          r(p.shirt, 7, 20, 19, 14);
          r(p.trim, 7, 30, 19, 5);
          r("#f0cdac", 4, 22, 4, 11);
          r("#f0cdac", 25, 22, 4, 11);
          r("#edc6a2", 8, 6, 17, 16);
          r("#f9dbb8", 10, 8, 13, 12);
          r(p.hair, 7, 2, 19, 7);
          r(p.hair, 5, 6, 6, 12);
          r(p.hair, 23, 6, 5, 12);
          r(p.hair, 10, 4, 13, 6);
          if (facing === "up") {
            r(p.hair, 8, 6, 17, 15);
          } else {
            const shift = facing === "left" ? -3 : facing === "right" ? 3 : 0;
            r("#30464c", 11 + shift, 13, 2, 3);
            r("#30464c", 20 + shift, 13, 2, 3);
            r("#cb947c", 16 + shift, 19, 3, 1);
          }
          if (template === "npc-bigfish") {
            r("#d4b48d", 6, 1, 22, 5);
            r("#dfc5a0", 9, -1, 16, 4);
            r("#678ca3", 4, 26, 5, 8);
            r("#678ca3", 25, 26, 5, 8);
          }
          if (template === "player") {
            r("#426d7e", 17, 23, 3, 8);
            r("#3c6472", 11, 21, 10, 3);
          }
          if (template === "npc-claude") {
            r("#a96b68", 9, 21, 15, 4);
            r("#b67b74", 12, 23, 4, 8);
          }
          tex.refresh();
        }
  }
  private makeProp(id: string, obj: BeachState["objects"][string]) {
    const g = this.add.graphics();
    const kind = obj.kind;
    if (kind === "berry") {
      g.fillStyle(0x547d4a, 0.25).fillEllipse(0, 12, 66, 20);
      for (const [x, y, w, h] of [
        [-28, -8, 22, 22],
        [-17, -23, 30, 30],
        [6, -15, 25, 26],
      ]) {
        g.fillStyle(0x39794f).fillRect(x, y, w, h);
        g.fillStyle(0x5c9855).fillRect(x, y, w, 8);
      }
      if (obj.remaining)
        for (const [x, y] of [
          [-18, -8],
          [5, -16],
          [18, -4],
          [-4, 3],
        ]) {
          g.fillStyle(0xd66a74).fillRect(x, y, 7, 7);
          g.fillStyle(0xf4a092).fillRect(x, y, 3, 3);
        }
    } else if (kind === "wood") {
      if (obj.remaining) {
        g.fillStyle(0xa38655).fillRect(-29, -6, 56, 13);
        g.fillStyle(0xd1b278).fillRect(-29, -6, 56, 4);
        g.fillStyle(0x796e48).fillRect(-21, 4, 44, 4);
        g.fillStyle(0xdac18d).fillRect(-31, -3, 6, 10);
        g.fillStyle(0x8d774b).fillRect(15, -13, 6, 13);
      }
    } else if (kind === "shell") {
      if (obj.remaining) {
        g.fillStyle(0xeaa28d).fillRect(-8, -5, 16, 10);
        g.fillStyle(0xf9dfbb).fillRect(-6, -8, 12, 9);
        g.fillStyle(0xc78577).fillRect(-2, -5, 3, 12);
      }
    } else if (kind === "crate") {
      g.fillStyle(0x917449).fillRect(-23, -22, 46, 44);
      g.fillStyle(0xc7a36a).fillRect(-22, -24, 44, 35);
      g.lineStyle(3, 0x8b7048).strokeRect(-22, -24, 44, 35);
      g.lineBetween(-20, -22, 20, 9).lineBetween(20, -22, -20, 9);
      g.fillStyle(0xe0c18a).fillRect(-23, -26, 46, 6);
      if (!obj.remaining) g.fillStyle(0x5d5946).fillRect(-18, -20, 36, 14);
    } else {
      g.fillStyle(0x947a51).fillRect(-4, -17, 8, 33);
      g.fillStyle(0xc4a36d).fillRect(-24, -30, 48, 22);
      g.fillStyle(0x796547).fillRect(-24, -12, 48, 4);
      g.lineStyle(2, 0x776746)
        .lineBetween(-15, -21, 14, -21)
        .lineBetween(14, -21, 8, -25)
        .lineBetween(14, -21, 8, -17);
    }
    const container = this.add.container(obj.x, obj.y, [g]).setDepth(obj.y + 1);
    this.props.set(id, container);
  }
  sync(state: BeachState) {
    const old = this.state;
    this.state = state;
    for (const [id, obj] of Object.entries(state.objects)) {
      if (
        !this.props.has(id) ||
        old?.objects[id]?.remaining !== obj.remaining
      ) {
        this.props.get(id)?.destroy(true);
        this.makeProp(id, obj);
      }
    }
    for (const [id, a] of Object.entries(state.actors)) {
      if (!this.actors.has(id)) {
        const sprite = this.add
          .sprite(a.x, a.y, `${a.template}-down-0`)
          .setOrigin(0.5, 0.9)
          .setScale(1.3)
          .setDepth(a.y + 2);
        this.actors.set(id, sprite);
        const label = this.add
          .text(a.x, a.y - 49, a.name, {
            fontSize: "11px",
            fontFamily: "Microsoft YaHei",
            color: "#234c53",
            backgroundColor: "#f6f4d7",
            padding: { x: 5, y: 3 },
          })
          .setOrigin(0.5)
          .setDepth(950);
        this.names.set(id, label);
      }
      const sprite = this.actors.get(id)!;
      const moving = Math.hypot(a.x - sprite.x, a.y - sprite.y) > 1;
      const texture = `${a.template}-${a.facing}-${moving ? state.tick % 3 : 0}`;
      if (this.textures.exists(texture)) sprite.setTexture(texture);
      this.tweens.killTweensOf(sprite);
      this.tweens.add({
        targets: sprite,
        x: a.x,
        y: a.y,
        duration: 100,
        ease: "Linear",
      });
      sprite.setDepth(a.y + 2);
      this.names.get(id)?.setPosition(a.x, a.y - 51);
    }
    for (const id of this.actors.keys())
      if (!state.actors[id]) {
        this.actors.get(id)!.destroy();
        this.actors.delete(id);
        this.names.get(id)?.destroy();
        this.names.delete(id);
      }
  }
  update(time: number) {
    if (!this.waves) return;
    this.keys.dx =
      Number(this.activeKeys.has("d") || this.activeKeys.has("arrowright")) -
      Number(this.activeKeys.has("a") || this.activeKeys.has("arrowleft"));
    this.keys.dy =
      Number(this.activeKeys.has("s") || this.activeKeys.has("arrowdown")) -
      Number(this.activeKeys.has("w") || this.activeKeys.has("arrowup"));
    if (time - this.tickAt > 150) {
      this.tickAt = time;
      this.waves.clear();
      for (let col = 0; col < 44; col++) {
        const x = col * 32,
          edge = (shore(col) + 1) * 32;
        const t = Math.floor(time / 350) % 5;
        this.waves
          .fillStyle(0xc7eee0, 0.6)
          .fillRect(x, edge + 8 + t * 3, 32, 3);
        if (col % 3 === 0)
          this.waves
            .fillStyle(0xa2dfe0, 0.7)
            .fillRect(
              x + 8,
              edge + 55 + Math.sin(time / 1000 + col) * 9,
              20,
              3,
            );
      }
    }
    this.overlay.clear();
    if (!this.state) return;
    const player = this.state.actors.player;
    const nearby = [
      ...Object.entries(this.state.objects).filter(
        ([, o]) => o.remaining || o.kind === "sign",
      ),
      ...Object.entries(this.state.actors).filter(([id]) => id !== "player"),
    ]
      .filter(
        ([, o]) =>
          Math.hypot(o.x - player.x, o.y - player.y) <=
          ("radius" in o ? Number(o.radius) : 90),
      )
      .sort(
        (a, b) =>
          Math.hypot(a[1].x - player.x, a[1].y - player.y) -
          Math.hypot(b[1].x - player.x, b[1].y - player.y),
      );
    if (nearby[0]) {
      const o = nearby[0][1];
      this.overlay
        .lineStyle(2, 0xfff2be, 0.9)
        .strokeEllipse(o.x, o.y + 8, 65, 25);
    }
    if (this.debug) {
      this.overlay.lineStyle(2, 0xe45c65, 0.7);
      for (const [x, y, w, h] of solids) this.overlay.strokeRect(x, y, w, h);
      for (const [, o] of Object.entries(this.state.objects))
        this.overlay
          .lineStyle(1, 0x2d8c99, 0.7)
          .strokeCircle(o.x, o.y, o.radius);
      for (const [, a] of Object.entries(this.state.actors))
        if (a.path?.length) {
          this.overlay.lineStyle(2, 0xf5e1a5, 0.9).beginPath().moveTo(a.x, a.y);
          for (const [x, y] of a.path) this.overlay.lineTo(x, y);
          this.overlay.strokePath();
        }
    }
  }
}
