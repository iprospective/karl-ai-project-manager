# frozen_string_literal: true
#
# Runner Rails — upsert idempotent du template global "Demande / CDC" du plugin
# redmine_issue_templates, sur N trackers, depuis une source canonique unique.
#
# Piloté par redmine-template-sync.py (ne pas lancer à la main). Toute la
# variabilité passe par l'environnement ; le corps markdown est lu depuis un
# fichier (jamais interpolé) pour éviter tout problème d'échappement.
#
#   TPL_BODY_PATH  chemin du fichier markdown canonique (corps de description)
#   TPL_TITLE      titre du template (clé d'unicité avec le tracker)
#   TPL_NOTE       mémo du template (varchar court)
#   TPL_AUTHOR     author_id Redmine
#   TPL_TRACKERS   ids de trackers séparés par des virgules (ex: "1,2,4")
#   TPL_DRY        "1" => n'écrit rien, rapporte seulement l'état (CREATE/UPDATE/UNCHANGED)

body      = File.read(ENV.fetch('TPL_BODY_PATH')).rstrip + "\n"
title     = ENV.fetch('TPL_TITLE')
note      = ENV['TPL_NOTE'].to_s
author_id = Integer(ENV.fetch('TPL_AUTHOR'))
trackers  = ENV.fetch('TPL_TRACKERS').split(',').map { |s| Integer(s.strip) }
dry       = ENV['TPL_DRY'] == '1'

proj_ids = Project.all.ids.sort

trackers.each do |tid|
  t = GlobalIssueTemplate.find_or_initialize_by(title: title, tracker_id: tid)
  new_rec   = t.new_record?
  cur_body  = t.description.to_s.rstrip + "\n"
  differs   = new_rec ||
              cur_body != body ||
              t.note.to_s != note ||
              t.is_default != true ||
              t.enabled != true ||
              t.project_ids.sort != proj_ids
  status = new_rec ? 'CREATE' : (differs ? 'UPDATE' : 'UNCHANGED')

  if dry || !differs
    puts "#{status} tracker=#{tid} title=#{title.inspect}#{t.id ? " id=#{t.id}" : ''}"
    next
  end

  t.description = body
  t.note        = note
  t.author_id   = author_id
  t.enabled     = true
  t.is_default  = true   # before_save :check_default rétrograde les autres défauts du tracker
  t.project_ids = proj_ids

  if t.save
    puts "#{status} tracker=#{tid} id=#{t.id} projets=#{t.project_ids.size}"
  else
    puts "ERROR  tracker=#{tid} -> #{t.errors.full_messages.join('; ')}"
  end
end
