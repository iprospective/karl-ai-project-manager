// services/projects.service — RM2889, L4.
import { ProjectsRepository } from "../models/projects/ProjectsRepository.js";
export class ProjectsService {
  constructor(repo = new ProjectsRepository()) { this.repo = repo; }
  all() { return this.repo.all(); }
  invalidate() { this.repo.store.invalidate(); }
}
