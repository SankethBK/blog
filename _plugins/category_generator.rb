module Jekyll
  class CategoryPageGenerator < Generator
    safe true

    def generate(site)

      puts "Plugin Generate running"
      if site.layouts.key? 'category'
        site.categories.keys.each do |category|
          site.pages << CategoryPage.new(site, site.source, 'categories', category)
        end
      end
    end
  end

  class CategoryPage < Page
    def initialize(site, base, dir, category)
      @site = site
      @base = base
      @dir = dir
      @name = "#{category}.html"

      self.process(@name)
      self.read_yaml(File.join(base, '_layouts'), 'category.html')
      self.data['category'] = category
    end
  end
end
