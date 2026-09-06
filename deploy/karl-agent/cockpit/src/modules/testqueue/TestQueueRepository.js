// models/testqueue/TestQueueRepository — RM2889.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get } from "../../core/api.js";
export class TestQueueRepository extends Repository {
  constructor() { super({ name: "test-queue", ttl: 5000, max: 2, factory: new Factory({ type: "tq-entry", required: ["rm_id"], defaults: { tags: [] } }), routes: { list: "pm.test_queue" } }); }
  async list() { const { queue } = await get(this.path("list")); return this.factory.many(queue || []); }
}
