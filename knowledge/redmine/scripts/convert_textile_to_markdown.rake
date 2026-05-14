# Patched: skip on pandoc failure (logs to /tmp/pandoc-failures.log)
task :convert_textile_to_markdown => :environment do
  convert = {
    Comment =>  [:content],
    WikiContent => [:text],
    Issue =>  [:description],
    Message => [:content],
    News => [:description],
    Document => [:description],
    Project => [:description],
    Journal => [:notes],
  }

  $pandoc_fail_log = File.open("/tmp/pandoc-failures.log", "w")
  $pandoc_fail_log.puts "model_class\tmodel_id\tattribute\tlen_textile"
  $pandoc_fail_count = 0

  count = 0
  print "WelcomeText"
  textile = Setting.welcome_text
  if textile != nil
    markdown = convert_textile_to_markdown(textile, "Setting", 0, "welcome_text")
    Setting.welcome_text = markdown unless markdown.nil?
  end
  count += 1
  print "."
  puts

  convert.each do |the_class, attributes|
    print the_class.name
    the_class.find_each do |model|
      attributes.each do |attribute|
        textile = model[attribute]
        if textile.nil? || textile.empty?
          next
        end
        markdown = convert_textile_to_markdown(textile, the_class.name, model.id, attribute)
        if markdown.nil?
          print "X"
        else
          model.update_column(attribute, markdown)
        end
      end
      count += 1
      print "."
    end
    puts
  end

  # WikiContentVersion — historique des pages wiki, accédé via .text (gère la compression gzip).
  # On préserve la compression d'origine par version pour ne toucher que la sémantique du contenu.
  require "zlib"
  print "WikiContentVersion"
  WikiContentVersion.find_each do |v|
    textile = v.text
    if textile.nil? || textile.empty?
      count += 1
      print "."
      next
    end
    markdown = convert_textile_to_markdown(textile, "WikiContentVersion", v.id, "text")
    if markdown.nil?
      print "X"
    else
      if v.compression == "gzip"
        v.update_columns(data: Zlib::Deflate.deflate(markdown, Zlib::BEST_COMPRESSION), compression: "gzip")
      else
        v.update_columns(data: markdown, compression: "")
      end
    end
    count += 1
    print "."
  end
  puts

  $pandoc_fail_log.close
  puts "Done converting #{count} models. Pandoc failures: #{$pandoc_fail_count} (see /tmp/pandoc-failures.log)"
end

def convert_textile_to_markdown(textile, model_class="?", model_id=0, attribute="?")
  require "tempfile"

  tag_code = "pandoc-unescaped-single-backtick"
  textile = textile.dup
  textile.gsub!(/@([\S]+@[\S]+)@/, tag_code + "\\1" + tag_code)
  textile.gsub!(/\|[\/\\\\]\d\. /, "| ")
  textile.gsub!(/\|[<>=]\. /, "| ")
  textile.gsub!(/(<pre)(><code)( class="[^"]*")(>)/, "\\1\\3\\2\\4")
  textile.gsub!(/(<pre[^>]*>)<code>/, "\\1")
  textile.gsub!(/<\/code>(<\/pre>)/, "\\1")
  tag_fenced_code_block = "force-pandoc-to-ouput-fenced-code-block"
  textile.gsub!(/([^\n]<pre)(>)/, "\\1 class=\"#{tag_fenced_code_block}\"\\2")
  textile.gsub!(/([^\n])(<pre)/, "\\1\n\n\\2")
  textile.gsub!(/-          # (\d+)/, "* \\1")

  src = Tempfile.new("src")
  src.write(textile)
  src.close
  dst = Tempfile.new("dst")
  dst.close

  command = [
    "pandoc",
    "--wrap=preserve",
    "-f", "textile",
    "-t", "gfm+smart",
    src.path,
    "-o", dst.path,
  ]

  ok = system(*command, :out => $stdout, :err => "/tmp/pandoc-stderr.log")
  unless ok
    $pandoc_fail_count += 1
    $pandoc_fail_log.puts "#{model_class}\t#{model_id}\t#{attribute}\t#{textile.length}"
    $pandoc_fail_log.flush
    src.unlink
    dst.unlink
    return nil
  end

  dst.open
  markdown = dst.read

  markdown.gsub!(/^((\\[*>])+)/) { $1.gsub("\\", "") }
  markdown.gsub!(/^([^*].*)\n\*/, "\\1\n\n*")
  markdown.gsub!(" " + tag_fenced_code_block, "")
  markdown.gsub!(tag_code, "`")
  markdown.gsub!("\\[\\[", "[[")
  markdown.gsub!("\\]\\]", "]]")
  # Un-escape underscores inside Redmine wiki links [[Page_Name|label]]
  # pandoc escapes _ to \_ everywhere; that breaks Redmine wiki link resolution.
  markdown.gsub!(/\[\[([^\]]+)\]\]/) { "[[#{$1.gsub('\\_', '_')}]]" }
  markdown.gsub!(/(^|\n)&gt; /, "\n> ")
  markdown.gsub!(/\n\n<!-- end list -->\n/, "\n")
  markdown.gsub!(/(https?:\/\/\S+)/) { |link| link.gsub(/\\([_#])/, "\\1") }

  return markdown
end
