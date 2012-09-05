require 'csl'

LOCALE_ROOT = File.expand_path('../..', __FILE__)

def load_locale(path)
  filename = File.basename(path)
  id = filename[0..-5]

  begin
    locale = CSL::Locale.load(path)
  rescue
    # failed to parse the locale. we'll report the error later
  end

  [id, [filename, path, locale]]
end


print "\nLoading locales"

Locales = Hash[Dir[File.join(LOCALE_ROOT, '*.xml')].each_with_index.map { |path, i|
  print '.' if i % 5 == 0
  load_locale(path)
}]

puts
